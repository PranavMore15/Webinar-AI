# Proposal

## Why

When users attempt to connect Google Drive from the dashboard (`/auth/gdrive/connect`), the application fails with `Failed to initiate Google OAuth: No module named 'google_auth_oauthlib'`. This occurs because `google-auth-oauthlib` and related Google Drive API packages (`google-api-python-client`, `google-auth`) were omitted from `requirements.txt` and are missing from environments installed from project dependencies.

## What Changes

- Declare official Google Drive OAuth and API packages in `requirements.txt`: `google-auth-oauthlib>=1.2.0`, `google-api-python-client>=2.100.0`, and `google-auth>=2.20.0`.
- Add explicit dependency check and user-friendly diagnostic error handling in `app/routes/auth_routes.py` for `/auth/gdrive/connect` and `/auth/gdrive/callback` so missing dependencies produce actionable remediation advice instead of raw module import errors.
- Document Google Drive OAuth prerequisites and environment setup in `README.md`.
- Add automated regression tests validating OAuth initiation and friendly error reporting when dependencies or client credentials are missing.

## Capabilities

### New Capabilities
- `media-retrieval`: Automated remote media ingestion and Google Drive OAuth connection capabilities, including runtime dependency safeguards and actionable diagnostics.

### Modified Capabilities

## Impact

- Dependencies: `requirements.txt` is updated with `google-auth-oauthlib>=1.2.0`, `google-api-python-client>=2.100.0`, and `google-auth>=2.20.0`.
- Application Code: `app/routes/auth_routes.py` handles `ImportError` gracefully when initiating Google OAuth or processing callback.
- Documentation: `README.md` documents Google Drive dependency requirements and setup.
- Testing: Regression test suite validates OAuth dependency checks and flow execution.
