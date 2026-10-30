"""
Google Gemini AI Summarization Service for WebinarAI.
Integrates with the official Google Gen AI Python SDK (`google-genai`), providing
structured educational summaries, context-aware chunking for long transcripts,
robust rate limit and error handling, and strict student data privacy.
"""

import os
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional
from flask import current_app
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# Constants
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_CHUNK_CHAR_LIMIT = 40000  # ~8,000 to 10,000 words
DEFAULT_CHUNK_OVERLAP = 2000
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 1.0

# Structured Educational Prompt Instructions
SYSTEM_INSTRUCTION = """You are an expert engineering educator and technical analyst.
Your task is to analyze webinar and lecture transcripts to produce clear, structured, and factual educational briefs.

Rules:
1. Summarize ONLY information and concepts supported by the supplied transcript.
2. Do NOT invent, assume, or hallucinate speakers, facts, technical claims, or conclusions.
3. If action items or next steps are mentioned in the transcript, list them in "action_items". If none are mentioned, return an empty list.
4. Extract important engineering and technical terminology with clear definitions directly based on the context.
5. Strictly output valid JSON adhering to the specified schema with all required keys.
"""

SUMMARY_PROMPT_TEMPLATE = """Analyze the following transcript from the webinar{title_context}.
Generate a comprehensive, structured educational summary in valid JSON format.

JSON Schema:
{{
  "title": "<Concise descriptive title of the webinar>",
  "overview": "<2-4 sentence executive overview of the webinar topic and primary purpose>",
  "key_points": [
    "<Key point 1>",
    "<Key point 2>"
  ],
  "takeaways": [
    "<Important technical takeaway 1>",
    "<Important technical takeaway 2>"
  ],
  "action_items": [
    "<Action item 1, if supported by the transcript>"
  ],
  "terminology": [
    {{
      "term": "<Important Technical Term>",
      "definition": "<Clear, concise definition based on the webinar discussion>"
    }}
  ],
  "conclusion": "<1-2 sentence concluding summary of the session>"
}}

Transcript Content:
---
{transcript}
---
"""

SYNTHESIS_PROMPT_TEMPLATE = """Below are intermediate summaries extracted from consecutive sections of a multi-part webinar transcript{title_context}.
Synthesize these section summaries into one cohesive, non-redundant, structured final educational summary.

JSON Schema:
{{
  "title": "<Final unified title of the webinar>",
  "overview": "<Comprehensive overview synthesizing all sections>",
  "key_points": [
    "<Synthesized key point 1>",
    "<Synthesized key point 2>"
  ],
  "takeaways": [
    "<Synthesized technical takeaway 1>",
    "<Synthesized technical takeaway 2>"
  ],
  "action_items": [
    "<Consolidated action items supported by the sections>"
  ],
  "terminology": [
    {{
      "term": "<Important Technical Term>",
      "definition": "<Clear, concise definition>"
    }}
  ],
  "conclusion": "<Cohesive final conclusion>"
}}

Section Summaries:
---
{intermediate_summaries}
---
"""


class GeminiConfigError(Exception):
    """Raised when required Gemini configuration or API key is missing."""
    pass


class GeminiValidationError(Exception):
    """Raised when transcript content or model output fails validation."""
    pass


class GeminiAPIError(Exception):
    """Raised when Gemini API communication fails or retries are exhausted."""
    pass


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

    return os.getenv('GEMINI_MODEL', DEFAULT_GEMINI_MODEL).strip()


def sanitize_text(text: str, secret: Optional[str] = None) -> str:
    """Sanitizes sensitive information from logs and error strings."""
    if not text:
        return ""
    if secret and secret in text:
        text = text.replace(secret, "[REDACTED_API_KEY]")
    return text


def validate_summary_data(data: Any) -> Dict[str, Any]:
    """
    Validates that parsed JSON data strictly conforms to the educational summary schema.
    Raises GeminiValidationError if invalid or missing required sections.
    """
    if not isinstance(data, dict):
        raise GeminiValidationError(f"Expected JSON object in model response, got {type(data).__name__}")

    required_keys = ['title', 'overview', 'key_points', 'takeaways', 'action_items', 'terminology', 'conclusion']
    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        raise GeminiValidationError(f"Summary output is missing required fields: {', '.join(missing_keys)}")

    # Validate title
    title = str(data.get('title', '')).strip()
    if not title:
        raise GeminiValidationError("Summary field 'title' must be a non-empty string.")

    # Validate overview
    overview = str(data.get('overview', '')).strip()
    if not overview:
        raise GeminiValidationError("Summary field 'overview' must be a non-empty string.")

    # Validate key_points (must be a list of non-empty strings)
    key_points = data.get('key_points')
    if not isinstance(key_points, list) or len(key_points) == 0:
        raise GeminiValidationError("Summary field 'key_points' must be a non-empty list of points.")
    cleaned_key_points = [str(p).strip() for p in key_points if str(p).strip()]
    if not cleaned_key_points:
        raise GeminiValidationError("Summary field 'key_points' contains no valid textual entries.")

    # Validate takeaways (must be a list of non-empty strings)
    takeaways = data.get('takeaways')
    if not isinstance(takeaways, list) or len(takeaways) == 0:
        raise GeminiValidationError("Summary field 'takeaways' must be a non-empty list of technical points.")
    cleaned_takeaways = [str(t).strip() for t in takeaways if str(t).strip()]
    if not cleaned_takeaways:
        raise GeminiValidationError("Summary field 'takeaways' contains no valid textual entries.")

    # Validate action_items (list of strings, can be empty)
    action_items = data.get('action_items')
    if not isinstance(action_items, list):
        action_items = []
    cleaned_action_items = [str(a).strip() for a in action_items if str(a).strip()]

    # Validate terminology (list of dicts with 'term' and 'definition')
    terminology = data.get('terminology')
    cleaned_terminology = []
    if isinstance(terminology, list):
        for item in terminology:
            if isinstance(item, dict) and item.get('term'):
                cleaned_terminology.append({
                    'term': str(item.get('term', '')).strip(),
                    'definition': str(item.get('definition', '')).strip()
                })
            elif isinstance(item, str) and ':' in item:
                parts = item.split(':', 1)
                cleaned_terminology.append({
                    'term': parts[0].strip(),
                    'definition': parts[1].strip()
                })

    # Validate conclusion
    conclusion = str(data.get('conclusion', '')).strip()
    if not conclusion:
        raise GeminiValidationError("Summary field 'conclusion' must be a non-empty string.")

    return {
        'title': title,
        'overview': overview,
        'key_points': cleaned_key_points,
        'takeaways': cleaned_takeaways,
        'action_items': cleaned_action_items,
        'terminology': cleaned_terminology,
        'conclusion': conclusion
    }


def chunk_transcript(
    text: str,
    max_chars: int = DEFAULT_CHUNK_CHAR_LIMIT,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP
) -> List[str]:
    """
    Splits long transcript text into sequential chunks along natural paragraph
    or sentence boundaries, ensuring continuity with a configurable overlap.
    """
    if not text:
        return []

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Ensure overlap does not exceed a reasonable fraction of max_chars
    effective_overlap = min(overlap_chars, max(0, max_chars // 5))
    search_window_size = min(max_chars // 2, 1500)

    chunks = []
    start = 0
    total_len = len(text)

    while start < total_len:
        end = start + max_chars
        if end >= total_len:
            remaining = text[start:].strip()
            if remaining:
                chunks.append(remaining)
            break

        # Look for natural split boundaries: paragraph first, then newline, then sentence period
        split_pos = -1
        window_start = max(start, end - search_window_size)
        search_window = text[window_start:end]
        
        # Priority 1: Double newline (paragraph boundary)
        p_offset = search_window.rfind('\n\n')
        if p_offset != -1:
            split_pos = window_start + p_offset + 2
        else:
            # Priority 2: Single newline
            n_offset = search_window.rfind('\n')
            if n_offset != -1:
                split_pos = window_start + n_offset + 1
            else:
                # Priority 3: Sentence ending period followed by space
                dot_match = [m.start() for m in re.finditer(r'\.\s+', search_window)]
                if dot_match:
                    split_pos = window_start + dot_match[-1] + 1

        if split_pos == -1 or split_pos <= start:
            split_pos = end

        chunk = text[start:split_pos].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start position taking overlap into account, ensuring forward progress
        next_start = split_pos - effective_overlap
        if next_start <= start:
            start = split_pos
        else:
            start = next_start

    return chunks


def call_gemini_generate(
    client: genai.Client,
    model: str,
    prompt: str,
    api_key: Optional[str] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY
) -> str:
    """
    Executes a content generation request to Gemini API with JSON mode,
    handling rate limits (HTTP 429) and transient errors with exponential backoff.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
        system_instruction=SYSTEM_INSTRUCTION
    )

    # Build list of fallback models preserving priority
    fallback_candidates = [model]
    for alt in ['gemini-3.6-flash', 'gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']:
        if alt not in fallback_candidates:
            fallback_candidates.append(alt)

    last_error = None
    last_status = None
    for current_model in fallback_candidates:
        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt,
                    config=config
                )

                if not response or not hasattr(response, 'text') or not response.text:
                    raise GeminiAPIError("Gemini API returned an empty response.")

                if current_model != model:
                    logger.info(f"Gemini API succeeded with fallback model '{current_model}' (requested: '{model}')")

                return response.text

            except genai_errors.APIError as e:
                last_error = e
                status_code = getattr(e, 'code', None)
                last_status = status_code
                err_msg = sanitize_text(str(e), api_key)

                # Check for Rate Limit (429) vs Server High Demand / Not Found (503/404)
                is_rate_limit = status_code == 429 or "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg
                is_server_error = status_code and 500 <= status_code < 600
                is_model_unavailable = status_code == 404

                # Standard rate limit retries with exponential backoff on current model
                if (is_rate_limit or is_server_error) and attempt < max_retries:
                    sleep_time = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Gemini API transient error for '{current_model}' (attempt {attempt}/{max_retries}, code {status_code}). "
                        f"Retrying in {sleep_time:.1f}s. Details: {err_msg}"
                    )
                    time.sleep(sleep_time)
                    continue

                # If rate limit (429) persists after all retries on the primary model, raise immediately
                if is_rate_limit:
                    raise GeminiAPIError(f"Gemini API call failed (HTTP {status_code}): {err_msg}") from e

                # If 503 (high demand) or 404 (unavailable), try the next candidate model
                if is_server_error or is_model_unavailable:
                    logger.warning(f"Model '{current_model}' failed with status {status_code}. Trying next candidate...")
                    break

                raise GeminiAPIError(f"Gemini API call failed (HTTP {status_code}): {err_msg}") from e

            except Exception as e:
                last_error = e
                err_msg = sanitize_text(str(e), api_key)
                if attempt < max_retries and ("timeout" in err_msg.lower() or "connection" in err_msg.lower()):
                    sleep_time = base_delay * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue
                break

    raise GeminiAPIError(f"Gemini API call failed (HTTP {last_status}): {sanitize_text(str(last_error), api_key)}")


def parse_and_validate_json_response(raw_response: str) -> Dict[str, Any]:
    """Parses raw text response as JSON and validates against educational schema."""
    if not raw_response or not raw_response.strip():
        raise GeminiValidationError("Received empty response string from Gemini model.")

    # Strip potential Markdown code blocks if model wrapped JSON in ```json ... ```
    cleaned_text = raw_response.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r'^```(?:json)?\s*', '', cleaned_text, flags=re.IGNORECASE)
        cleaned_text = re.sub(r'\s*```$', '', cleaned_text)

    try:
        parsed_data = json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        raise GeminiValidationError(f"Failed to parse Gemini output as JSON: {e}") from e

    return validate_summary_data(parsed_data)


def summarize_transcript(
    transcript_text: str,
    title_hint: Optional[str] = None,
    client: Optional[genai.Client] = None,
    model: Optional[str] = None,
    chunk_char_limit: int = DEFAULT_CHUNK_CHAR_LIMIT
) -> Dict[str, Any]:
    """
    Main summarization entry point.
    Processes cleaned transcript text, handles chunking if required, calls Gemini,
    validates the output, and returns a verified structured summary dictionary.
    
    Guarantees:
    - Never passes recipient CSV data or student PII to Gemini.
    - Masks secrets from error reporting.
    - Validates presence of necessary text content.
    """
    # Step 1: Validate input transcript presence
    if not transcript_text or not transcript_text.strip():
        raise GeminiValidationError("Transcript content is empty. Cannot summarize an empty transcript.")

    words = transcript_text.strip().split()
    if len(words) < 5:
        raise GeminiValidationError("Transcript contains insufficient spoken text (less than 5 words) to summarize.")

    # Step 2: Validate API key and Model configuration
    api_key = get_gemini_api_key()
    if not api_key:
        raise GeminiConfigError(
            "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in the environment or .env file."
        )

    resolved_model = model or get_gemini_model()

    # Step 3: Initialize GenAI client if not supplied
    if client is None:
        client = genai.Client(api_key=api_key)

    title_context = f" titled '{title_hint.strip()}'" if title_hint and title_hint.strip() else ""

    # Step 4: Determine single-pass vs. chunked processing
    chunks = chunk_transcript(transcript_text, max_chars=chunk_char_limit)

    if len(chunks) == 1:
        # Single-pass execution
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            title_context=title_context,
            transcript=chunks[0]
        )
        raw_output = call_gemini_generate(
            client=client,
            model=resolved_model,
            prompt=prompt,
            api_key=api_key
        )
        return parse_and_validate_json_response(raw_output)

    # Multi-chunk synthesis execution
    logger.info(f"Transcript exceeds {chunk_char_limit} characters. Performing multi-chunk synthesis across {len(chunks)} sections.")
    intermediate_summaries = []

    for idx, chunk in enumerate(chunks, 1):
        chunk_prompt = SUMMARY_PROMPT_TEMPLATE.format(
            title_context=f"{title_context} (Part {idx} of {len(chunks)})",
            transcript=chunk
        )
        raw_chunk_output = call_gemini_generate(
            client=client,
            model=resolved_model,
            prompt=chunk_prompt,
            api_key=api_key
        )
        chunk_summary = parse_and_validate_json_response(raw_chunk_output)
        intermediate_summaries.append(
            f"--- Part {idx} Summary ---\n"
            f"Overview: {chunk_summary['overview']}\n"
            f"Key Points: {'; '.join(chunk_summary['key_points'])}\n"
            f"Takeaways: {'; '.join(chunk_summary['takeaways'])}\n"
            f"Action Items: {'; '.join(chunk_summary['action_items']) if chunk_summary['action_items'] else 'None'}\n"
            f"Terminology: {json.dumps(chunk_summary['terminology'])}\n"
            f"Conclusion: {chunk_summary['conclusion']}\n"
        )

    # Final synthesis call combining intermediate parts
    synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        title_context=title_context,
        intermediate_summaries="\n\n".join(intermediate_summaries)
    )

    final_raw_output = call_gemini_generate(
        client=client,
        model=resolved_model,
        prompt=synthesis_prompt,
        api_key=api_key
    )

    return parse_and_validate_json_response(final_raw_output)


def get_summary_folder() -> str:
    """Returns the absolute path to storage/summaries/."""
    try:
        folder = current_app.config.get('SUMMARY_FOLDER')
        if folder:
            os.makedirs(folder, exist_ok=True)
            return folder
    except RuntimeError:
        pass

    default_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage', 'summaries')
    os.makedirs(default_folder, exist_ok=True)
    return default_folder


def get_summary_path(job_id: int) -> str:
    """Returns the target JSON file path for a job's summary."""
    return os.path.join(get_summary_folder(), f"job_{job_id}_summary.json")


def save_job_summary(job_id: int, summary_data: Dict[str, Any]) -> str:
    """Persists validated summary dictionary to storage/summaries/job_{job_id}_summary.json."""
    file_path = get_summary_path(job_id)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    return file_path


def load_job_summary(job_id: int) -> Optional[Dict[str, Any]]:
    """Loads persisted summary dictionary for a given job if available."""
    file_path = get_summary_path(job_id)
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def process_job_summarization(
    job: Any,
    client: Optional[genai.Client] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Orchestrates the Prompt 5 processing pipeline for a ProcessingJob:
    1. Extracts or parses transcript using Prompt 4 pipeline (process_webinar_to_transcript).
    2. Updates job.transcript_status = 'completed'.
    3. Calls Gemini API to generate structured educational summary.
    4. Persists summary JSON file to storage/summaries/job_{job.id}_summary.json.
    5. Updates job.summary_status = 'completed' (or 'failed' on error).
    6. Commits changes to the database.
    """
    from app.models import db, ProcessingJob
    from app.services.transcript_service import process_webinar_to_transcript

    if isinstance(job, int):
        job = ProcessingJob.query.get(job)
        if not job:
            raise ValueError(f"ProcessingJob with id={job} not found.")

    try:
        # Step 1: Ingest or transcribe webinar content
        transcript_res = process_webinar_to_transcript(job.input_type, job.input_file_path)
        transcript_text = transcript_res.get('transcript_text', '')
        job.transcript_status = 'completed'

        # Step 2: Invoke Gemini summarization
        job.summary_status = 'generating'
        db.session.commit()

        title_hint = job.title or job.input_file_name
        summary_result = summarize_transcript(
            transcript_text=transcript_text,
            title_hint=title_hint,
            client=client,
            model=model
        )

        # Step 3: Persist summary JSON artifact
        summary_file_path = save_job_summary(job.id, summary_result)

        # Step 4: Update job statuses
        job.summary_status = 'completed'
        job.error_message = None
        db.session.commit()

        return {
            'success': True,
            'job_id': job.id,
            'summary_file_path': summary_file_path,
            'summary': summary_result
        }

    except Exception as e:
        db.session.rollback()
        err_msg = sanitize_text(str(e))
        job.summary_status = 'failed'
        job.error_message = f"AI Summarization Failed: {err_msg}"
        db.session.commit()
        logger.error(f"Job {job.id} summarization failed: {err_msg}")
        raise
