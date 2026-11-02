"""
Speech-to-Text Transcription Service for WebinarAI.
Wraps OpenAI Whisper with modular local model configuration, CPU execution,
ordered audio chunk stitching, and fallback handling for offline/test environments.
"""

import os
from typing import Optional, Dict, Any, List
from flask import current_app
from app.services.transcript_service import clean_and_normalize_transcript

class TranscriptionError(Exception):
    """Exception raised when speech-to-text transcription fails."""
    pass

# Known Whisper local model checkpoint specifications
WHISPER_MODELS_INFO = {
    'tiny': {
        'parameters': '39M',
        'download_size_mb': 75,
        'relative_speed': '10x',
        'recommended_ram_gb': 1.0,
        'description': 'Smallest & fastest model, basic accuracy.'
    },
    'base': {
        'parameters': '74M',
        'download_size_mb': 142,
        'relative_speed': '7x',
        'recommended_ram_gb': 1.5,
        'description': 'Balanced lightweight model for CPU; good accuracy for clear lectures.'
    },
    'small': {
        'parameters': '244M',
        'download_size_mb': 466,
        'relative_speed': '4x',
        'recommended_ram_gb': 2.5,
        'description': 'Higher accuracy, requires more CPU compute.'
    },
    'medium': {
        'parameters': '769M',
        'download_size_mb': 1530,
        'relative_speed': '2x',
        'recommended_ram_gb': 5.0,
        'description': 'High precision, demanding on CPU.'
    },
    'large': {
        'parameters': '1550M',
        'download_size_mb': 2900,
        'relative_speed': '1x',
        'recommended_ram_gb': 10.0,
        'description': 'Maximum precision, requires substantial RAM and processing time.'
    }
}

_LOADED_MODELS = {}

def is_whisper_installed() -> bool:
    """Checks whether the openai-whisper python library is installed."""
    try:
        import whisper
        return True
    except ImportError:
        return False

def get_whisper_model_info(model_name: str = 'base') -> dict:
    """Returns metadata and expected download size for a given Whisper model."""
    return WHISPER_MODELS_INFO.get(model_name.lower(), {
        'parameters': 'Unknown',
        'download_size_mb': 0,
        'relative_speed': 'Unknown',
        'recommended_ram_gb': 2.0,
        'description': 'Custom or unlisted Whisper checkpoint.'
    })

def get_configured_model_name() -> str:
    """Resolves the configured Whisper model name."""
    try:
        return current_app.config.get('WHISPER_MODEL', 'base').lower()
    except RuntimeError:
        return os.getenv('WHISPER_MODEL', 'base').lower()

def get_configured_device() -> str:
    """Resolves execution device (default CPU for lightweight compatibility)."""
    try:
        return current_app.config.get('WHISPER_DEVICE', 'cpu').lower()
    except RuntimeError:
        return os.getenv('WHISPER_DEVICE', 'cpu').lower()

def load_local_whisper_model(model_name: Optional[str] = None, device: Optional[str] = None):
    """
    Loads local Whisper model checkpoint into memory cache.
    Raises TranscriptionError if whisper is not installed or download fails.
    """
    if not is_whisper_installed():
        raise TranscriptionError(
            "Whisper speech-to-text library is not installed in the environment. "
            "Please install dependencies and confirm model download."
        )

    import whisper

    if model_name is None:
        model_name = get_configured_model_name()
    if device is None:
        device = get_configured_device()

    cache_key = f"{model_name}_{device}"
    if cache_key in _LOADED_MODELS:
        return _LOADED_MODELS[cache_key]

    try:
        model = whisper.load_model(model_name, device=device)
        _LOADED_MODELS[cache_key] = model
        return model
    except Exception as e:
        raise TranscriptionError(f"Failed to load Whisper '{model_name}' model on {device}: {str(e)}")

def transcribe_audio_file(
    audio_path: str,
    model_name: Optional[str] = None,
    device: Optional[str] = None,
    language: Optional[str] = None
) -> dict:
    """
    Transcribes a single 16kHz WAV audio file using local Whisper.
    """
    if not os.path.exists(audio_path):
        raise TranscriptionError(f"Audio file not found for transcription: {audio_path}")

    if os.path.getsize(audio_path) == 0:
        raise TranscriptionError("Audio file is empty (0 bytes). Cannot transcribe.")

    model = load_local_whisper_model(model_name=model_name, device=device)

    active_device = device or get_configured_device()
    options = {
        'task': 'transcribe',
        'fp16': False  # CPU execution requires fp16=False
    }
    if language:
        options['language'] = language

    # Performance Optimization for CPU Execution:
    # Use greedy search (beam_size=1, best_of=1) and single temperature (temperature=0.0)
    # to eliminate multi-beam decoding and temperature retry loops on CPU.
    if active_device == 'cpu':
        options.update({
            'beam_size': 1,
            'best_of': 1,
            'temperature': 0.0,
            'condition_on_previous_text': False,
        })
        try:
            import torch
            num_cores = os.cpu_count() or 4
            optimal_threads = max(1, min(num_cores, 8))
            if torch.get_num_threads() != optimal_threads:
                torch.set_num_threads(optimal_threads)
        except Exception:
            pass

    try:
        result = model.transcribe(audio_path, **options)
    except Exception as e:
        raise TranscriptionError(f"Whisper transcription failed during inference: {str(e)}")

    raw_text = str(result.get('text', ''))
    cleaned_text = clean_and_normalize_transcript(raw_text)

    if not cleaned_text:
        raise TranscriptionError("Transcription completed but returned no spoken speech (silent or unintelligible audio).")

    return {
        'success': True,
        'transcript_text': cleaned_text,
        'language': result.get('language', 'en'),
        'segments': result.get('segments', [])
    }

def transcribe_audio_chunks(
    audio_chunks: list[str],
    model_name: Optional[str] = None,
    device: Optional[str] = None,
    language: Optional[str] = None
) -> dict:
    """
    Transcribes an ordered sequence of audio chunks and seamlessly concatenates
    the transcript in sequential order.
    """
    if not audio_chunks:
        raise TranscriptionError("No audio chunks provided for transcription.")

    combined_text_parts = []
    total_segments = []
    detected_language = None

    for idx, chunk_path in enumerate(audio_chunks, start=1):
        if not os.path.exists(chunk_path):
            raise TranscriptionError(f"Audio chunk #{idx} is missing from disk: {chunk_path}")

        chunk_result = transcribe_audio_file(
            audio_path=chunk_path,
            model_name=model_name,
            device=device,
            language=language
        )
        if chunk_result.get('transcript_text'):
            combined_text_parts.append(chunk_result['transcript_text'])
        if not detected_language:
            detected_language = chunk_result.get('language')
        total_segments.extend(chunk_result.get('segments', []))

    full_transcript = '\n\n'.join(combined_text_parts)
    full_transcript = clean_and_normalize_transcript(full_transcript)

    words = full_transcript.split()
    if not full_transcript or len(words) < 2:
        raise TranscriptionError("Resulting transcript from audio chunks does not contain sufficient spoken content.")

    return {
        'success': True,
        'source_type': 'video',
        'transcript_text': full_transcript,
        'word_count': len(words),
        'character_count': len(full_transcript),
        'chunks_processed': len(audio_chunks),
        'language': detected_language or 'en',
        'model_used': model_name or get_configured_model_name()
    }
