# Proposal: Automated Webinar Video Retrieval and Processing

## Why

Currently, WebinarAI users must manually locate, download, and re-upload large webinar recordings or transcripts from external hosting platforms (such as university servers, video hosting sites, or cloud drives) to the application dashboard. This manual download-upload cycle creates substantial friction, consumes unnecessary client bandwidth, and limits usability on constrained devices.

Providing an automated retrieval mechanism where users simply input a recording location (direct media URL, YouTube link, Google Drive link, or browser-selected local file/folder) allows WebinarAI to verify access permissions, check technical compatibility, and retrieve the media directly into the existing summarization and knowledge-distribution pipeline without manual intermediary handling.

## What Changes

- **Webinar Content Source Dashboard UI**: Extend the existing dashboard with a dedicated "Webinar Content Source" section featuring 6 distinct input modes:
  1. Direct Video/Audio Link (MP4, MP3, WAV, M4A, etc.)
  2. YouTube Link (standard watch URLs, youtu.be, shorts)
  3. Google Drive Link (file-sharing URLs via official Google Drive API and OAuth 2.0)
  4. Local Computer Files (browser file picker)
  5. Local Computer Folders (browser folder selector with media filtering)
  6. Existing Manual Uploads (retaining full support for MP4 video, TXT, and VTT transcript files)
- **Pre-Flight Accessibility Check**: Add an explicit "Check Accessibility" action to verify source reachability, MIME types, file size limits, and authorization constraints before processing is triggered.
- **Direct Media Retrieval Engine & SSRF Protection**: Implement a hardened retrieval service with comprehensive Server-Side Request Forgery (SSRF) protections, including loopback and RFC 1918 private address blocking, DNS re-validation, redirect re-validation, restricted ports, content-type inspection, and streaming size limits.
- **Official Google Drive Integration**: Implement secure OAuth 2.0 user authorization and official Google Drive API retrieval for authorized media files, supporting account disconnection and secure token management.
- **YouTube Compliance & Caption Handling**: Implement official YouTube API metadata and caption inspection. Strictly prohibit unauthorized video downloading, scraping, `yt-dlp`, or DRM circumvention, offering authorized caption processing or manual upload alternatives when automated video retrieval is disallowed.
- **Browser-Supported Local Folder Processing**: Allow users to select local folders via browser-supported directory pickers, inspect files, select the specific webinar recording, and transfer only the chosen file to the backend.
- **Processing Job & Pipeline Extension**: Extend `ProcessingJob` tracking to record source type, original reference, retrieval status, and file metadata while seamlessly passing retrieved media to the existing FFmpeg/Whisper audio extraction, Gemini summarization, ReportLab PDF, and SMTP email distribution workflow.
- **Full Backward Compatibility**: Preserve all existing manual upload options, CSV recipient validation, and role-based access control.

## Capabilities

### New Capabilities
- `media-retrieval`: Automated and authorized ingestion of webinar media from direct URLs, YouTube, Google Drive, and local computer selections, including SSRF protection, access verification, streaming retrieval, and pipeline handoff.

### Modified Capabilities
<!-- None. No existing specs in openspec/specs/. -->

## Impact

- **Backend Architecture**: Introduces modular providers under `app/providers/` (direct, YouTube, Google Drive, local) and retrieval coordination services under `app/services/` with SSRF utility under `app/utils/ssrf.py`.
- **Database Schema**: Extends `ProcessingJob` in `app/models/schema.py` to record `source_type`, `source_url`, `retrieval_status`, and media metadata.
- **User Interface**: Enhances `app/templates/dashboard.html` and `app/static/js/dashboard.js` with responsive source selector cards, accessibility inspection controls, and live status displays.
- **External Dependencies & APIs**: Requires official `google-api-python-client` and `google-auth-oauthlib` for Google Drive OAuth. Strictly avoids unauthorized scraping packages.
- **Security & Privacy**: Enforces SSRF defense, prevents private network probing, protects OAuth tokens, validates MIME content signatures, and ensures student recipient data remains strictly segregated.

