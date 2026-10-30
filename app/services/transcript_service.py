"""
Transcript Processing Service for WebinarAI.
Handles parsing, cleaning, and normalization of TXT and WebVTT (.vtt) transcripts.
Guarantees preservation of spoken sentences and speaker labels while stripping
timestamps, formatting artifacts, and cue metadata.
"""

import os
import re
import html

class TranscriptParseError(Exception):
    """Exception raised when transcript parsing or validation fails."""
    pass

def read_file_with_fallback(file_path: str) -> str:
    """Reads a text file trying multiple standard encodings."""
    if not os.path.exists(file_path):
        raise TranscriptParseError(f"Transcript file not found: {file_path}")

    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    if not raw_bytes:
        raise TranscriptParseError("Transcript file is empty (0 bytes).")

    for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252'):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue

    raise TranscriptParseError("Failed to decode transcript file with supported encodings (UTF-8, Latin-1, CP1252).")

def clean_and_normalize_transcript(text: str) -> str:
    """
    Normalizes whitespace and standardizes transcript text:
    - Normalizes line endings to \n
    - Strips non-printable ASCII control characters (preserving newlines and tabs)
    - Collapses multiple empty lines
    - Trims leading/trailing whitespace
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Remove non-printable control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    # Decode HTML entities if present
    text = html.unescape(text)

    # Collapse consecutive horizontal whitespace (spaces/tabs)
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]

    # Collapse multiple blank lines to a single blank line
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned_lines.append("")
                prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False

    return '\n'.join(cleaned_lines).strip()

def parse_txt_transcript(file_path: str) -> dict:
    """
    Parses a plain text (.txt) transcript file.
    Validates content presence and calculates metadata.
    """
    raw_text = read_file_with_fallback(file_path)
    cleaned_text = clean_and_normalize_transcript(raw_text)

    words = cleaned_text.split()
    if not cleaned_text or len(words) < 2:
        raise TranscriptParseError("Transcript does not contain sufficient spoken text content.")

    return {
        'success': True,
        'source_type': 'txt',
        'file_path': file_path,
        'transcript_text': cleaned_text,
        'word_count': len(words),
        'character_count': len(cleaned_text),
        'speaker_labels': extract_speaker_labels(cleaned_text)
    }

def parse_vtt_transcript(file_path: str) -> dict:
    """
    Parses a WebVTT (.vtt) subtitle/caption transcript file.
    Requirements:
    1. Removes WEBVTT header and header metadata/comments (NOTE, STYLE, REGION).
    2. Removes cue identifiers (e.g. sequence numbers or cue names).
    3. Removes cue timestamps (e.g. '00:00:01.000 --> 00:00:05.500').
    4. Preserves speaker labels (e.g. 'Dr. Jane Doe: ...' or '<v Jane>...</v>' -> 'Jane: ...').
    5. Strips inline formatting tags (<b>, <i>, <c.color>, etc.) and timing tags.
    6. Deduplicates adjacent repeated caption lines.
    7. Validates meaningful spoken content.
    """
    raw_content = read_file_with_fallback(file_path)
    lines = raw_content.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    # Timestamp pattern: matches "00:00:00.000 --> 00:00:04.000" with optional hours and settings
    timestamp_pattern = re.compile(
        r'^\s*(?:\d{1,2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+(?:\d{1,2}:)?\d{2}:\d{2}\.\d{3}'
    )

    # Voice tag pattern: <v Speaker Name>Speech</v> or <v.class Speaker>Speech
    voice_tag_pattern = re.compile(r'<v(?:(?:\.[^\s>]+)|\s+([^>]+))>(.*?)(?:</v>)?', re.IGNORECASE)

    # General HTML/VTT tag pattern: e.g. <c.yellow>, </b>, <00:01:02.000>
    tag_pattern = re.compile(r'<[^>]+>')

    parsed_speech_lines = []
    in_header = True
    in_block_comment = False
    cue_count = 0

    for raw_line in lines:
        line = raw_line.strip()

        # Handle header block (starts with WEBVTT)
        if in_header:
            if line.upper().startswith('WEBVTT'):
                continue
            # Header metadata lines (e.g. "Kind: captions" or empty line ending header)
            if line == '':
                in_header = False
                continue
            if ':' in line and not timestamp_pattern.match(line):
                # Header metadata key-value
                continue
            # If line matches cue or content, exit header
            in_header = False

        if not line:
            in_block_comment = False
            continue

        # Handle NOTE / STYLE / REGION blocks
        if line.startswith('NOTE') or line.startswith('STYLE') or line.startswith('REGION'):
            in_block_comment = True
            continue

        if in_block_comment:
            continue

        # Check for timestamp line
        if timestamp_pattern.search(line):
            cue_count += 1
            # If the preceding line was just a cue identifier (e.g. a number or ID), remove it
            if parsed_speech_lines and is_cue_identifier(parsed_speech_lines[-1]):
                parsed_speech_lines.pop()
            continue

        # Convert WebVTT voice tags <v Speaker Name>Text to "Speaker Name: Text"
        def voice_replacer(match):
            speaker = match.group(1) or ""
            speech = match.group(2) or ""
            if speaker.strip():
                return f"{speaker.strip()}: {speech.strip()}"
            return speech.strip()

        processed_line = voice_tag_pattern.sub(voice_replacer, line)

        # Remove remaining inline tags (<b>, <i>, <c>, etc.)
        processed_line = tag_pattern.sub('', processed_line).strip()

        # Decode HTML entities
        processed_line = html.unescape(processed_line)

        if not processed_line:
            continue

        # Deduplicate adjacent identical lines (standard in rolling broadcast captions)
        if parsed_speech_lines and parsed_speech_lines[-1] == processed_line:
            continue

        parsed_speech_lines.append(processed_line)

    # Final cleanup of any trailing cue IDs
    while parsed_speech_lines and is_cue_identifier(parsed_speech_lines[-1]):
        parsed_speech_lines.pop()

    cleaned_text = '\n'.join(parsed_speech_lines).strip()
    cleaned_text = clean_and_normalize_transcript(cleaned_text)

    words = cleaned_text.split()
    if not cleaned_text or len(words) < 2:
        raise TranscriptParseError("WebVTT file does not contain usable spoken transcript content after stripping cues.")

    return {
        'success': True,
        'source_type': 'vtt',
        'file_path': file_path,
        'transcript_text': cleaned_text,
        'word_count': len(words),
        'character_count': len(cleaned_text),
        'cue_count': cue_count,
        'speaker_labels': extract_speaker_labels(cleaned_text)
    }

def is_cue_identifier(line: str) -> bool:
    """Detects if a single line is an isolated cue identifier (number or simple token)."""
    line = line.strip()
    if not line:
        return False
    # Pure numeric sequence ID (e.g., "1", "42")
    if line.isdigit():
        return True
    # Short alphanumeric cue ID (e.g., "cue-1", "intro-01") with no spaces or sentence punctuation
    if re.match(r'^[a-zA-Z0-9_\-]+$', line) and len(line) < 30 and ' ' not in line:
        return True
    return False

def extract_speaker_labels(text: str) -> list[str]:
    """
    Extracts distinct speaker labels if formatted as:
    1. Explicit metadata lines: 'Speaker: <Name>' or 'Presenter: <Name>'
    2. Dialogue attribution lines: '<Speaker Name>: <Speech>'
    Filters out document header keywords like 'Webinar Title', 'Topic', etc.
    Returns a sorted list of unique speaker names.
    """
    EXCLUDED_PREFIXES = {'webinar title', 'title', 'topic', 'date', 'overview', 'summary', 'conclusion', 'note', 'takeaways'}
    speakers = set()

    # 1. Explicit metadata lines (e.g. "Speaker: Dr. Alan Turing")
    explicit_matches = re.findall(r'^(?:Speaker|Presenter):\s*([A-Za-z0-9\.\s]{2,40})$', text, re.MULTILINE | re.IGNORECASE)
    for name in explicit_matches:
        cleaned = name.strip()
        if cleaned:
            speakers.add(cleaned)

    # 2. Dialogue lines (e.g. "Dr. Jane Doe: Good morning...")
    dialogue_matches = re.findall(r'^([A-Z][a-zA-Z0-9\.\s]{1,30}):\s+[A-Za-z]', text, re.MULTILINE)
    for name in dialogue_matches:
        cleaned = name.strip(' :')
        if cleaned.lower() not in EXCLUDED_PREFIXES and cleaned.lower() not in ('speaker', 'presenter'):
            speakers.add(cleaned)

    return sorted(list(speakers))

def parse_transcript_by_type(file_path: str, input_type: str = None) -> dict:
    """
    Unified router that parses either TXT or VTT based on extension or explicit type.
    """
    if not input_type:
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    else:
        ext = input_type.lower()

    if ext in ('vtt', 'webvtt'):
        return parse_vtt_transcript(file_path)
    elif ext in ('txt', 'transcript'):
        return parse_txt_transcript(file_path)
    else:
        raise TranscriptParseError(f"Unsupported transcript format '.{ext}'. Supported formats are .txt and .vtt.")

def process_webinar_to_transcript(input_type: str, file_path: str) -> dict:
    """
    Unified processing entry point for Prompt 4:
    - If input_type == 'transcript': parses TXT or VTT directly; DOES NOT invoke FFmpeg or Whisper.
    - If input_type == 'video': extracts audio via FFmpeg, chunks if needed, and transcribes via Whisper.
    """
    if input_type == 'transcript':
        return parse_transcript_by_type(file_path)
    elif input_type == 'video':
        from app.services import audio_service, transcription_service
        audio_info = audio_service.extract_audio_from_video(file_path)
        audio_path = audio_info['audio_path']
        chunks = []
        try:
            chunks = audio_service.chunk_audio_if_needed(audio_path)
            result = transcription_service.transcribe_audio_chunks(chunks)
            return result
        finally:
            to_delete = list(set([audio_path] + chunks))
            audio_service.delete_audio_files(to_delete)
    else:
        raise TranscriptParseError(f"Unknown input type '{input_type}'. Must be 'video' or 'transcript'.")
