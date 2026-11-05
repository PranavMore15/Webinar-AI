# Design

## Context

WebinarAI supports Google Drive as an automated recording source via `GDriveMediaProvider` (`app/providers/gdrive_provider.py`) and OAuth 2.0 connection endpoints (`app/routes/auth_routes.py`). These components import `google_auth_oauthlib`, `googleapiclient`, and `google.oauth2.credentials`.

However, `requirements.txt` currently lacks entries for `google-auth-oauthlib` and `google-api-python-client`. When an environment is provisioned using `pip install -r requirements.txt`, or when the application runs in an environment where these libraries are absent, accessing `/auth/gdrive/connect` raises an unhandled `ModuleNotFoundError` caught by a generic exception handler, flashing `Failed to initiate Google OAuth: No module named 'google_auth_oauthlib'`.

See `proposal.md` for motivation and `specs/media-retrieval/spec.md` for normative requirements.

## Goals / Non-Goals

**Goals:**
- Include official Google Drive and OAuth packages in `requirements.txt` with compatible version constraints.
- Provide defensive import handling in `app/routes/auth_routes.py` with actionable remediation guidance when packages are missing.
- Clarify setup steps and virtual environment activation in `README.md`.
- Provide automated regression test coverage for OAuth initiation and dependency validation.

**Non-Goals:**
- Modifying the underlying Google Drive API retrieval pipeline or download streaming logic in `gdrive_provider.py`.
- Changing OAuth scopes or security model (remains minimal `https://www.googleapis.com/auth/drive.readonly`).
- Managing Google OAuth credentials or tokens in the codebase (credentials remain configured via environment variables).

## Decisions

### Decision 1: Declare Google Drive dependencies in `requirements.txt`
- **Choice**: Add `google-auth>=2.20.0`, `google-auth-oauthlib>=1.2.0`, and `google-api-python-client>=2.100.0` directly to `requirements.txt` under a dedicated `Prompt A4: Google Drive Integration` section.
- **Rationale**: Google Drive is a first-class source option on the dashboard alongside YouTube and Direct URLs. Missing dependencies in the primary manifest lead to runtime errors for anyone setting up the application fresh.
- **Alternatives Considered**: 
  - *Separate optional requirements file (`requirements-optional.txt`)*: Rejected because Google Drive retrieval is already integrated into the dashboard UI and core providers.

### Decision 2: Structured `ImportError` handling with actionable guidance in OAuth routes
- **Choice**: In `app/routes/auth_routes.py` (`gdrive_connect` and `gdrive_callback`), explicitly intercept `ImportError` (or `ModuleNotFoundError`) before general `Exception`.
- **Rationale**: Rather than displaying raw Python errors (`No module named 'google_auth_oauthlib'`), the UI will flash:
  `"Google Drive OAuth packages are missing. Please install dependencies with: pip install -r requirements.txt"`.
- **Alternatives Considered**:
  - *Global top-level imports in `auth_routes.py`*: Rejected because failing imports at module load time would crash the entire application at startup if Google Drive is not used. Keeping dynamic/guarded imports allows the rest of the application (transcription, summarization, YouTube, manual uploads) to continue functioning even if Drive dependencies are missing.

### Decision 3: Document setup and virtual environment usage
- **Choice**: Update `README.md` to document the required Google Drive packages and remind users to run within their activated virtual environment (`.venv`).
- **Rationale**: Many users experience module not found errors when running `python run.py` using system Python rather than the virtual environment where dependencies were installed.

## Risks / Trade-offs

- **[Risk]** Version conflict between `google-genai` and `google-auth-oauthlib` / `google-api-python-client`.
  → **Mitigation**: Verified against project `.venv` where `google-genai 2.31.0`, `google-auth 2.62.0`, `google-api-python-client 2.201.0`, and `google-auth-oauthlib 1.5.0` coexist without version conflicts. Standard loose `>=` bounds avoid locking constraints.

- **[Risk]** Users running without configuring `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
  → **Mitigation**: Ensure `auth_routes.py` checks for client credentials and provides a clear message if environment variables are not set before attempting the OAuth flow.
