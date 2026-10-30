"""
Audio Processing & Extraction Service for WebinarAI.
Handles FFmpeg audio extraction from MP4 webinars, duration detection,
and audio chunking for speech-to-text processing.
"""

import os
import shutil
import subprocess
import uuid
import re
from flask import current_app

class AudioProcessingError(Exception):
    """Exception raised when FFmpeg audio extraction or processing fails."""
    pass

def get_ffmpeg_executable() -> str:
    """Resolves path to FFmpeg binary using config, environment, or PATH."""
    try:
        configured = current_app.config.get('FFMPEG_PATH')
        if configured and os.path.exists(configured):
            return configured
    except RuntimeError:
        pass

    env_path = os.getenv('FFMPEG_PATH')
    if env_path and os.path.exists(env_path):
        return env_path

    # Common Windows install locations
    for common_loc in (
        r'C:\Apps\ffmpeg\bin\ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe'
    ):
        if os.path.exists(common_loc):
            return common_loc

    which_ffmpeg = shutil.which('ffmpeg')
    if which_ffmpeg:
        return which_ffmpeg

    raise AudioProcessingError(
        "FFmpeg binary not found on system. Please ensure FFmpeg is installed and accessible."
    )

def get_ffprobe_executable() -> str:
    """Resolves path to FFprobe binary."""
    try:
        configured = current_app.config.get('FFPROBE_PATH')
        if configured and os.path.exists(configured):
            return configured
    except RuntimeError:
        pass

    env_path = os.getenv('FFPROBE_PATH')
    if env_path and os.path.exists(env_path):
        return env_path

    for common_loc in (
        r'C:\Apps\ffmpeg\bin\ffprobe.exe',
        r'C:\ffmpeg\bin\ffprobe.exe'
    ):
        if os.path.exists(common_loc):
            return common_loc

    which_ffprobe = shutil.which('ffprobe')
    if which_ffprobe:
        return which_ffprobe

    # If ffprobe is not found, fallback to ffmpeg which can also probe
    return get_ffmpeg_executable()

def extract_audio_from_video(video_path: str, output_folder: str = None, timeout_seconds: int = 300) -> dict:
    """
    Extracts audio track from an MP4 video file and converts it into 16kHz mono WAV,
    the optimal standard format for OpenAI Whisper speech-to-text transcription.
    
    Returns:
        dict: {
            'success': True,
            'audio_path': str,
            'audio_format': 'wav',
            'sample_rate': 16000,
            'channels': 1,
            'file_size': int,
            'duration_seconds': float
        }
    """
    if not os.path.exists(video_path):
        raise AudioProcessingError(f"Video file does not exist: {video_path}")

    ffmpeg_bin = get_ffmpeg_executable()

    if output_folder is None:
        try:
            output_folder = current_app.config.get('AUDIO_FOLDER', os.path.join('storage', 'audio'))
        except RuntimeError:
            output_folder = os.path.join('storage', 'audio')

    os.makedirs(output_folder, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    unique_id = uuid.uuid4().hex[:10]
    output_audio_path = os.path.join(output_folder, f"{unique_id}_{base_name}_audio.wav")

    # Command: extract audio, discard video (-vn), 16kHz mono PCM 16-bit WAV
    cmd = [
        ffmpeg_bin,
        '-y',               # Overwrite output without asking
        '-i', video_path,   # Input video
        '-vn',              # No video
        '-acodec', 'pcm_s16le',
        '-ar', '16000',     # 16,000 Hz sample rate
        '-ac', '1',         # 1 audio channel (mono)
        output_audio_path
    ]

    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired:
        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)
        raise AudioProcessingError(f"FFmpeg audio extraction timed out after {timeout_seconds} seconds.")
    except Exception as e:
        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)
        raise AudioProcessingError(f"Failed to execute FFmpeg command: {str(e)}")

    if process.returncode != 0:
        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)
        err_msg = process.stderr or process.stdout or "Unknown FFmpeg error."
        # Check if video contains no audio stream
        if "does not contain any stream" in err_msg or "Output file is empty" in err_msg or "matches no streams" in err_msg:
            raise AudioProcessingError("The uploaded MP4 video does not contain an audio stream.")
        raise AudioProcessingError(f"FFmpeg audio extraction failed (exit code {process.returncode}): {err_msg[:400]}")

    if not os.path.exists(output_audio_path) or os.path.getsize(output_audio_path) == 0:
        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)
        raise AudioProcessingError("FFmpeg completed but generated an empty (0-byte) audio output.")

    # Get duration
    duration = get_audio_duration(output_audio_path)

    return {
        'success': True,
        'audio_path': output_audio_path,
        'audio_format': 'wav',
        'sample_rate': 16000,
        'channels': 1,
        'file_size': os.path.getsize(output_audio_path),
        'duration_seconds': duration
    }

def get_audio_duration(audio_path: str) -> float:
    """Calculates duration in seconds using ffprobe or ffmpeg probe."""
    if not os.path.exists(audio_path):
        return 0.0

    probe_bin = get_ffprobe_executable()
    # If ffprobe is available, use fast JSON/value probe
    if probe_bin.endswith('ffprobe.exe') or probe_bin.endswith('ffprobe'):
        cmd = [
            probe_bin,
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass

    # Fallback to ffmpeg -i parsing
    ffmpeg_bin = get_ffmpeg_executable()
    try:
        res = subprocess.run([ffmpeg_bin, '-i', audio_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', res.stderr)
        if match:
            hours, mins, secs = match.groups()
            return int(hours) * 3600 + int(mins) * 60 + float(secs)
    except Exception:
        pass

    return 0.0

def chunk_audio_if_needed(audio_path: str, chunk_length_seconds: int = 600, output_folder: str = None) -> list[str]:
    """
    Splits long audio into sequential chunks of chunk_length_seconds (default 10 mins).
    If audio duration is less than or equal to chunk_length_seconds, returns [audio_path].
    """
    duration = get_audio_duration(audio_path)
    if duration <= chunk_length_seconds or duration == 0.0:
        return [audio_path]

    ffmpeg_bin = get_ffmpeg_executable()
    if output_folder is None:
        output_folder = os.path.dirname(audio_path)

    os.makedirs(output_folder, exist_ok=True)
    chunks = []
    base_name = os.path.splitext(os.path.basename(audio_path))[0]

    current_start = 0.0
    chunk_index = 1

    while current_start < duration:
        chunk_file = os.path.join(output_folder, f"{base_name}_chunk_{chunk_index:03d}.wav")
        cmd = [
            ffmpeg_bin,
            '-y',
            '-ss', str(current_start),
            '-t', str(chunk_length_seconds),
            '-i', audio_path,
            '-acodec', 'copy',
            chunk_file
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        if res.returncode == 0 and os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
            chunks.append(chunk_file)
        else:
            # If copy failed, try re-encoding chunk
            cmd_reencode = [
                ffmpeg_bin,
                '-y',
                '-ss', str(current_start),
                '-t', str(chunk_length_seconds),
                '-i', audio_path,
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                chunk_file
            ]
            res_re = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if res_re.returncode == 0 and os.path.exists(chunk_file):
                chunks.append(chunk_file)
            else:
                break

        current_start += chunk_length_seconds
        chunk_index += 1

    return chunks if chunks else [audio_path]

def delete_audio_files(file_paths: list[str]) -> None:
    """Safely cleans up generated audio files from disk."""
    for path in file_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
