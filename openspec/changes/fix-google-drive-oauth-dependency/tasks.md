# Tasks

## 1. Dependency Management

- [x] 1.1 Add Google Drive dependencies (`google-auth>=2.20.0`, `google-auth-oauthlib>=1.2.0`, `google-api-python-client>=2.100.0`) to `requirements.txt` under `Prompt A4: Google Drive Integration` and verify syntax.
- [x] 1.2 Verify package availability in the virtual environment by running an import verification command (`python -c "import google_auth_oauthlib, googleapiclient; print('Google libraries imported successfully')"`).

## 2. Route Guarding and Diagnostic Error Handling

- [x] 2.1 Update `app/routes/auth_routes.py` `gdrive_connect` route to catch `ImportError` and flash an actionable remediation message (`"Google Drive OAuth packages are missing. Please install dependencies with: pip install -r requirements.txt"`) instead of raw module errors.
- [x] 2.2 Update `app/routes/auth_routes.py` `gdrive_callback` route to handle `ImportError` gracefully during token exchange with actionable guidance.
- [x] 2.3 Verify credentials check in `gdrive_connect` when `GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_SECRET` is missing or unconfigured, providing a clear prompt before OAuth flow generation.

## 3. Documentation and Regression Testing

- [x] 3.1 Update `README.md` to document Google Drive OAuth prerequisites, required packages in `requirements.txt`, and virtual environment activation steps.
- [x] 3.2 Add automated unit and regression tests in `tests/test_gdrive_integration.py` asserting proper error flashing and redirects when Google OAuth packages are missing or credentials are unconfigured.
- [x] 3.3 Run the full test suite (`pytest`) to verify all existing and new tests pass cleanly.
