# Spec Delta

## Purpose

Provides authorized automated ingestion of webinar video and audio from remote sources including Google Drive, enforcing dependency verification, robust OAuth connectivity, and clear error reporting.

## ADDED Requirements

### Requirement: Google Drive Dependency Availability and Verification
The system SHALL ensure that all dependencies necessary for Google Drive OAuth flow and Google Drive API retrieval are packaged and resolvable in the application runtime environment.

#### Scenario: Dependency manifest includes Google Drive libraries
- **WHEN** the project dependencies are installed from the dependency manifest
- **THEN** google-auth-oauthlib and google-api-python-client packages are installed and importable by the application

#### Scenario: Missing dependency diagnostic error handling
- **WHEN** a user triggers the Google Drive OAuth flow and a required OAuth package is not installed in the runtime environment
- **THEN** the system catches the import failure, flashes an actionable error message directing the user or administrator to install required dependencies, and safely redirects to the dashboard without an unhandled server exception

### Requirement: Google Drive OAuth Connection Initiation
The system SHALL initiate the Google OAuth 2.0 authorization code flow with the required drive readonly scope when requested by an authenticated user.

#### Scenario: Successful OAuth initiation
- **WHEN** an authenticated user clicks to connect their Google Drive account and required libraries are installed and configured
- **THEN** the system generates a secure state, constructs the Google OAuth consent URL, and redirects the user to the consent screen

#### Scenario: Missing OAuth client credentials
- **WHEN** an authenticated user clicks to connect their Google Drive account but Google client ID or secret is not configured
- **THEN** the system displays a descriptive flash message informing the user that Google Drive credentials are not configured and redirects to the dashboard
