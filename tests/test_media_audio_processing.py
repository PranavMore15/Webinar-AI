import os
import io
import shutil
import tempfile
import unittest
import subprocess
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import TestConfig
from app.services import transcript_service, audio_service, transcription_service
from app.services.transcript_service import (
    parse_txt_transcript,
    parse_vtt_transcript,
    clean_and_normalize_transcript,
    process_webinar_to_transcript,
    TranscriptParseError
)
from app.services.audio_service import (
    get_ffmpeg_executable,
    get_audio_duration,
    extract_audio_from_video,
    chunk_audio_if_needed,
    AudioProcessingError
)
from app.services.transcription_service import (
    get_whisper_model_info,
    get_configured_model_name,
    get_configured_device,
    transcribe_audio_chunks,
    TranscriptionError
)

class TestMediaAudioProcessing(unittest.TestCase):
    """
    Automated test suite for Prompt 4: Media & Audio Processing.
    Tests TXT/VTT parsing and normalization, FFmpeg audio extraction,
    duration detection, audio chunking, and Whisper service configuration.
    """
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.app = create_app(TestConfig)
        self.app.config['AUDIO_FOLDER'] = os.path.join(self.temp_dir, 'audio')
        os.makedirs(self.app.config['AUDIO_FOLDER'], exist_ok=True)
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # TXT Transcript Parsing Tests
    # -------------------------------------------------------------------------
    def test_parse_valid_txt_transcript(self):
        txt_path = os.path.join(self.temp_dir, 'sample.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("Webinar Title: Neural Networks in Production\nSpeaker: Dr. Andrew Ng\nDeep learning models require careful data validation and monitoring.")

        result = parse_txt_transcript(txt_path)
        self.assertTrue(result['success'])
        self.assertEqual(result['source_type'], 'txt')
        self.assertIn("Neural Networks in Production", result['transcript_text'])
        self.assertGreater(result['word_count'], 10)
        self.assertIn('Dr. Andrew Ng', result['speaker_labels'])

    def test_parse_txt_with_different_encodings(self):
        # Test latin-1 encoding with special characters
        txt_path = os.path.join(self.temp_dir, 'encoded_latin1.txt')
        with open(txt_path, 'wb') as f:
            f.write("Résumé of the lecture on distributed systems: naïve algorithms fail under network partitions.".encode('latin-1'))

        result = parse_txt_transcript(txt_path)
        self.assertTrue(result['success'])
        self.assertIn("distributed systems", result['transcript_text'])

    def test_parse_txt_empty_or_whitespace_raises_error(self):
        empty_path = os.path.join(self.temp_dir, 'empty.txt')
        with open(empty_path, 'w', encoding='utf-8') as f:
            f.write("   \n\t   \n")

        with self.assertRaises(TranscriptParseError):
            parse_txt_transcript(empty_path)

    def test_parse_txt_missing_file_raises_error(self):
        missing_path = os.path.join(self.temp_dir, 'nonexistent.txt')
        with self.assertRaises(TranscriptParseError):
            parse_txt_transcript(missing_path)

    # -------------------------------------------------------------------------
    # VTT Transcript Parsing & Normalization Tests
    # -------------------------------------------------------------------------
    def test_parse_valid_vtt_transcript_cues_and_speakers(self):
        vtt_content = """WEBVTT - Distributed Systems Workshop
Kind: captions
Language: en

1
00:00:01.000 --> 00:00:04.500
Dr. Jane Doe: Good morning and welcome to our systems lecture.

2
00:00:05.000 --> 00:00:09.000
<v Prof. Turing>Today we analyze Byzantine fault tolerance.</v>

00:00:09.500 --> 00:00:14.000
<b>Prof. Turing:</b> <c.yellow>Consensus algorithms</c.yellow> are fundamental.
"""
        vtt_path = os.path.join(self.temp_dir, 'lecture.vtt')
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write(vtt_content)

        result = parse_vtt_transcript(vtt_path)
        self.assertTrue(result['success'])
        self.assertEqual(result['source_type'], 'vtt')
        self.assertEqual(result['cue_count'], 3)

        # Timestamps and numeric cue IDs must be removed
        self.assertNotIn("00:00:01.000", result['transcript_text'])
        self.assertNotIn("-->", result['transcript_text'])
        self.assertNotIn("WEBVTT", result['transcript_text'])

        # Formatting tags must be removed
        self.assertNotIn("<b>", result['transcript_text'])
        self.assertNotIn("<c.yellow>", result['transcript_text'])

        # Spoken text and speakers must be preserved
        self.assertIn("Good morning and welcome to our systems lecture.", result['transcript_text'])
        self.assertIn("Prof. Turing: Today we analyze Byzantine fault tolerance.", result['transcript_text'])
        self.assertIn("Consensus algorithms are fundamental.", result['transcript_text'])
        self.assertIn('Dr. Jane Doe', result['speaker_labels'])
        self.assertIn('Prof. Turing', result['speaker_labels'])

    def test_parse_vtt_deduplicates_adjacent_identical_lines(self):
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello engineers.

00:00:03.000 --> 00:00:05.000
Hello engineers.

00:00:05.000 --> 00:00:08.000
Welcome to class.
"""
        vtt_path = os.path.join(self.temp_dir, 'repeating.vtt')
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write(vtt_content)

        result = parse_vtt_transcript(vtt_path)
        lines = result['transcript_text'].split('\n')
        self.assertEqual(lines.count("Hello engineers."), 1)
        self.assertEqual(lines.count("Welcome to class."), 1)

    def test_parse_vtt_without_cues_or_text_raises_error(self):
        vtt_path = os.path.join(self.temp_dir, 'no_cues.vtt')
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT - Header Only\n\nNOTE comment\n")

        with self.assertRaises(TranscriptParseError):
            parse_vtt_transcript(vtt_path)

    # -------------------------------------------------------------------------
    # Specification Requirement: Transcripts Must NOT Invoke FFmpeg/Whisper
    # -------------------------------------------------------------------------
    @patch('app.services.audio_service.extract_audio_from_video')
    @patch('app.services.transcription_service.load_local_whisper_model')
    def test_transcript_input_does_not_invoke_ffmpeg_or_whisper(self, mock_whisper, mock_ffmpeg):
        vtt_path = os.path.join(self.temp_dir, 'sample.vtt')
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nSpoken content here for testing.\n")

        result = process_webinar_to_transcript('transcript', vtt_path)
        self.assertTrue(result['success'])
        # Neither FFmpeg nor Whisper may be called for transcript uploads
        mock_ffmpeg.assert_not_called()
        mock_whisper.assert_not_called()

    # -------------------------------------------------------------------------
    # FFmpeg Audio Extraction Tests
    # -------------------------------------------------------------------------
    def test_ffmpeg_executable_resolution(self):
        ffmpeg_bin = get_ffmpeg_executable()
        self.assertTrue(os.path.exists(ffmpeg_bin))
        self.assertTrue(ffmpeg_bin.lower().endswith('ffmpeg.exe') or ffmpeg_bin.lower().endswith('ffmpeg'))

    def test_ffmpeg_extract_audio_from_synthetic_video(self):
        """Creates a synthetic test MP4 with audio and tests FFmpeg extraction."""
        ffmpeg_bin = get_ffmpeg_executable()
        test_video_path = os.path.join(self.temp_dir, 'synthetic_video.mp4')

        # Generate a 2-second test MP4 containing video + audio
        cmd = [
            ffmpeg_bin, '-y',
            '-f', 'lavfi', '-i', 'testsrc=duration=2:size=320x240:rate=10',
            '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=2',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            test_video_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, f"Synthetic MP4 generation failed: {res.stderr}")
        self.assertTrue(os.path.exists(test_video_path))

        # Extract audio using service
        extracted = extract_audio_from_video(test_video_path, output_folder=self.app.config['AUDIO_FOLDER'])
        self.assertTrue(extracted['success'])
        self.assertEqual(extracted['audio_format'], 'wav')
        self.assertEqual(extracted['sample_rate'], 16000)
        self.assertEqual(extracted['channels'], 1)
        self.assertGreater(extracted['file_size'], 1000)
        self.assertAlmostEqual(extracted['duration_seconds'], 2.0, delta=0.5)

        # Verify output exists
        self.assertTrue(os.path.exists(extracted['audio_path']))

    def test_ffmpeg_missing_video_raises_error(self):
        with self.assertRaises(AudioProcessingError):
            extract_audio_from_video(os.path.join(self.temp_dir, 'nonexistent.mp4'))

    def test_ffmpeg_video_without_audio_stream_raises_error(self):
        """Tests MP4 without audio stream."""
        ffmpeg_bin = get_ffmpeg_executable()
        video_no_audio = os.path.join(self.temp_dir, 'video_no_audio.mp4')
        cmd = [
            ffmpeg_bin, '-y',
            '-f', 'lavfi', '-i', 'testsrc=duration=1:size=160x120:rate=5',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            video_no_audio
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        self.assertEqual(res.returncode, 0)

        with self.assertRaises(AudioProcessingError) as ctx:
            extract_audio_from_video(video_no_audio, output_folder=self.app.config['AUDIO_FOLDER'])
        self.assertIn("does not contain an audio stream", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Audio Chunking & Duration Tests
    # -------------------------------------------------------------------------
    def test_audio_chunking_short_file_returns_single_chunk(self):
        # Create a 2-second WAV
        ffmpeg_bin = get_ffmpeg_executable()
        wav_path = os.path.join(self.temp_dir, 'short.wav')
        subprocess.run([
            ffmpeg_bin, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
            '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_path
        ], check=True)

        chunks = chunk_audio_if_needed(wav_path, chunk_length_seconds=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], wav_path)

    def test_audio_chunking_long_file_splits_sequentially(self):
        # Create a 6-second WAV and chunk by 2 seconds
        ffmpeg_bin = get_ffmpeg_executable()
        wav_path = os.path.join(self.temp_dir, 'long.wav')
        subprocess.run([
            ffmpeg_bin, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
            '-c:a', 'pcm_s16le', '-ar', '16000', '-ac', '1', wav_path
        ], check=True)

        chunks = chunk_audio_if_needed(wav_path, chunk_length_seconds=2, output_folder=self.temp_dir)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertTrue(os.path.exists(chunk))

    # -------------------------------------------------------------------------
    # Whisper Configuration & Transcription Service Tests
    # -------------------------------------------------------------------------
    def test_whisper_model_info_inspection(self):
        base_info = get_whisper_model_info('base')
        self.assertEqual(base_info['download_size_mb'], 142)
        self.assertEqual(base_info['parameters'], '74M')

        tiny_info = get_whisper_model_info('tiny')
        self.assertEqual(tiny_info['download_size_mb'], 75)

    def test_whisper_configuration_defaults(self):
        self.assertEqual(get_configured_model_name(), 'base')
        self.assertEqual(get_configured_device(), 'cpu')

    @patch('app.services.transcription_service.transcribe_audio_file')
    def test_transcribe_audio_chunks_sequential_stitching(self, mock_transcribe_file):
        # Mock transcription of 3 ordered chunks
        chunk1 = os.path.join(self.temp_dir, 'chunk1.wav')
        chunk2 = os.path.join(self.temp_dir, 'chunk2.wav')
        for c in (chunk1, chunk2):
            with open(c, 'wb') as f:
                f.write(b'RIFF_DUMMY_AUDIO_DATA')

        mock_transcribe_file.side_effect = [
            {'success': True, 'transcript_text': 'Introduction to Cloud Architectures and microservices.', 'language': 'en'},
            {'success': True, 'transcript_text': 'Database sharding provides horizontal scalability across clusters.', 'language': 'en'}
        ]

        result = transcribe_audio_chunks([chunk1, chunk2], model_name='base')
        self.assertTrue(result['success'])
        self.assertEqual(result['chunks_processed'], 2)
        self.assertIn('Introduction to Cloud Architectures', result['transcript_text'])
        self.assertIn('Database sharding provides horizontal scalability', result['transcript_text'])
        self.assertGreater(result['word_count'], 10)

    # -------------------------------------------------------------------------
    # Full Video Pipeline Integration with Mock Transcription
    # -------------------------------------------------------------------------
    @patch('app.services.transcription_service.transcribe_audio_chunks')
    def test_full_video_pipeline_with_audio_extraction_and_cleanup(self, mock_transcribe):
        # Create synthetic test MP4 with audio
        ffmpeg_bin = get_ffmpeg_executable()
        test_video = os.path.join(self.temp_dir, 'full_lecture.mp4')
        subprocess.run([
            ffmpeg_bin, '-y',
            '-f', 'lavfi', '-i', 'testsrc=duration=2:size=160x120:rate=5',
            '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=2',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            test_video
        ], check=True)

        mock_transcribe.return_value = {
            'success': True,
            'source_type': 'video',
            'transcript_text': 'Today we will discuss operating system kernels and process scheduling.',
            'word_count': 10,
            'character_count': 68,
            'chunks_processed': 1,
            'language': 'en',
            'model_used': 'base'
        }

        result = process_webinar_to_transcript('video', test_video)
        self.assertTrue(result['success'])
        self.assertIn('operating system kernels', result['transcript_text'])

        # Verify that temporary extracted audio files in AUDIO_FOLDER were cleaned up
        audio_files = os.listdir(self.app.config['AUDIO_FOLDER'])
        self.assertEqual(len(audio_files), 0, "Extracted audio files must be cleaned up after pipeline completes.")

    # -------------------------------------------------------------------------
    # Real CPU Whisper Transcription Integration Test (Non-Mocked)
    # -------------------------------------------------------------------------
    def test_real_cpu_transcription_with_downloaded_whisper_base_model(self):
        """
        Real end-to-end CPU transcription test using the downloaded Whisper base model.
        Generates spoken audio via Windows Speech and verifies live inference on CPU.
        """
        import whisper
        from app.services.transcription_service import transcribe_audio_file

        speech_wav = os.path.join(self.temp_dir, 'live_test_speech.wav')
        # Generate spoken audio using Windows Speech
        try:
            ps_script = f'''
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile("{speech_wav}")
$synth.Speak("Hello engineering students. This is a real Whisper transcription test.")
$synth.Dispose()
'''
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, timeout=15)
        except Exception:
            self.skipTest("PowerShell System.Speech unavailable in test environment.")

        self.assertTrue(os.path.exists(speech_wav))

        # Run real CPU Whisper transcription
        result = transcribe_audio_file(speech_wav, model_name='base', device='cpu')
        self.assertTrue(result['success'])
        self.assertGreater(len(result['transcript_text']), 0)
        # Verify transcribed content contains spoken keywords
        transcribed_lower = result['transcript_text'].lower()
        self.assertTrue(
            'hello' in transcribed_lower or 'engineering' in transcribed_lower or 'whisper' in transcribed_lower,
            f"Expected keywords in transcript, got: {result['transcript_text']}"
        )

if __name__ == '__main__':
    unittest.main()
