"""
Speech-to-Text Transcription Service for WebinarAI.
Wraps OpenAI Whisper with modular local model configuration, CPU execution,
ordered audio chunk stitching, and fallback handling for offline/test environments.
"""

import os
import logging
from typing import Optional, Dict, Any, List, Callable
from flask import current_app
from app.services.transcript_service import clean_and_normalize_transcript

logger = logging.getLogger(__name__)

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

def get_gemini_api_key() -> Optional[str]:
    """Retrieves GEMINI_API_KEY from Flask current_app config or os.environ."""
    try:
        key = current_app.config.get('GEMINI_API_KEY')
        if key and key.strip():
            return key.strip()
    except RuntimeError:
        pass

    key = os.getenv('GEMINI_API_KEY')
    return key.strip() if key and key.strip() else None

def get_gemini_model() -> str:
    """Retrieves GEMINI_MODEL from Flask current_app config or os.environ."""
    try:
        model = current_app.config.get('GEMINI_MODEL')
        if model and model.strip():
            return model.strip()
    except RuntimeError:
        pass

    return os.getenv('GEMINI_MODEL', 'gemini-3.6-flash').strip()

def parse_gemini_transcript_response(response_text: str) -> str:
    """
    Extracts and standardizes transcript text from Gemini API response.
    Handles raw text, markdown blocks, and JSON-wrapped transcript envelopes.
    """
    if not response_text:
        return ""

    raw = response_text.strip()
    # Check if enclosed in markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        if len(lines) >= 3 and lines[-1].strip() == "```":
            fence_lang = lines[0].lstrip("`").strip().lower()
            inner = "\n".join(lines[1:-1]).strip()
            if fence_lang == "json" or (inner.startswith("{") and inner.endswith("}")):
                try:
                    import json
                    parsed = json.loads(inner)
                    if isinstance(parsed, dict):
                        return parsed.get("transcript") or parsed.get("text") or inner
                except Exception:
                    pass
            raw = inner

    # Check for direct JSON { "transcript": "..." } or { "text": "..." }
    if raw.startswith("{") and raw.endswith("}"):
        try:
            import json
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and ("transcript" in parsed or "text" in parsed):
                return str(parsed.get("transcript") or parsed.get("text") or "")
        except Exception:
            pass

    return raw

def transcribe_audio_with_gemini(
    audio_path: str,
    model_name: Optional[str] = None,
    client: Optional[Any] = None
) -> dict:
    """
    Transcribes audio using Google Gemini multimodal audio processing.
    Uploads audio file using Google Gen AI File API, requests verbatim transcript,
    and guarantees immediate remote file deletion in finally block.
    """
    if not os.path.exists(audio_path):
        raise TranscriptionError(f"Audio file not found for Gemini transcription: {audio_path}")

    if os.path.getsize(audio_path) == 0:
        raise TranscriptionError("Audio file is empty (0 bytes). Cannot transcribe.")

    api_key = get_gemini_api_key()
    if not api_key:
        raise TranscriptionError("GEMINI_API_KEY is not configured for Gemini speech-to-text.")

    from google import genai
    from google.genai import types

    if client is None:
        client = genai.Client(api_key=api_key)

    resolved_model = model_name or get_gemini_model()
    uploaded_file = None

    try:
        uploaded_file = client.files.upload(file=audio_path)
        system_instruction = (
            "You are an expert speech-to-text transcription engine. "
            "Your task is to listen to the provided audio file and generate an accurate, verbatim transcript "
            "of all spoken speech. Maintain proper capitalization and punctuation. "
            "Preserve speaker labels if distinguishable (e.g., 'Speaker 1:', 'Dr. Smith:'). "
            "Output ONLY the transcript text without any introductory comments or conversational filler."
        )
        prompt = (
            "Transcribe all speech from this audio recording verbatim. "
            "Do not summarize. Provide the complete transcript text."
        )

        response = client.models.generate_content(
            model=resolved_model,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0
            )
        )
    except Exception as e:
        raise TranscriptionError(f"Gemini API audio transcription failed: {str(e)}")
    finally:
        if uploaded_file is not None and hasattr(client, 'files'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as del_err:
                logger.warning(f"Failed to delete uploaded Gemini file {getattr(uploaded_file, 'name', '')}: {del_err}")

    raw_output = getattr(response, 'text', '') or ''
    extracted_text = parse_gemini_transcript_response(raw_output)
    cleaned_text = clean_and_normalize_transcript(extracted_text)

    words = cleaned_text.split()
    if not cleaned_text or len(words) < 2:
        raise TranscriptionError("Transcription completed but returned no spoken speech (silent or unintelligible audio).")

    return {
        'success': True,
        'source_type': 'video',
        'transcript_text': cleaned_text,
        'word_count': len(words),
        'character_count': len(cleaned_text),
        'chunks_processed': 1,
        'language': 'en',
        'model_used': resolved_model,
        'engine': 'gemini'
    }

def transcribe_audio_chunks(
    audio_chunks: list[str],
    model_name: Optional[str] = None,
    device: Optional[str] = None,
    language: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None
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
    total_chunks = len(audio_chunks)

    for idx, chunk_path in enumerate(audio_chunks, start=1):
        if not os.path.exists(chunk_path):
            raise TranscriptionError(f"Audio chunk #{idx} is missing from disk: {chunk_path}")

        if progress_callback:
            progress_callback(f"Transcribing audio chunk {idx} of {total_chunks} with local Whisper AI...")

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
        'model_used': model_name or get_configured_model_name(),
        'engine': 'whisper'
    }

def transcribe_audio_hybrid(
    audio_path: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    model_name: Optional[str] = None
) -> dict:
    """
    Hybrid speech-to-text dispatcher:
    1. Attempts high-speed Gemini multimodal audio transcription if GEMINI_API_KEY is configured.
    2. Gracefully falls back to local Whisper CPU transcription if Gemini fails, offline, or unconfigured.
    """
    api_key = get_gemini_api_key()
    is_testing = False
    try:
        is_testing = current_app.config.get('TESTING', False)
    except RuntimeError:
        pass

    if api_key and not is_testing:
        try:
            if progress_callback:
                progress_callback("Transcribing speech with Gemini AI (high-speed path)...")
            logger.info("Initiating Gemini AI audio speech transcription...")
            return transcribe_audio_with_gemini(audio_path, model_name=model_name)
        except Exception as e:
            logger.warning(
                f"Gemini speech transcription failed or unavailable: {str(e)}. "
                "Switching to local Whisper speech-to-text fallback."
            )
            if progress_callback:
                progress_callback("Gemini API unavailable. Falling back to local Whisper speech-to-text...")

    # Fallback to local Whisper
    if progress_callback:
        progress_callback("Transcribing speech with local Whisper AI...")

    from app.services import audio_service
    chunks = audio_service.chunk_audio_if_needed(audio_path)
    try:
        return transcribe_audio_chunks(chunks, progress_callback=progress_callback)
    finally:
        if chunks and chunks != [audio_path]:
            audio_service.delete_audio_files(chunks)
