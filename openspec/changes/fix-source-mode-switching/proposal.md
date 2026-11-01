# Proposal

## Why

Users clicking on the YouTube icon or other additional source selectors (Direct Link, Google Drive, Local File, Local Folder) in Section A of the dashboard experience no response, and the "Manual Format Mode" upload controls remain persistently visible. This occurs because duplicate element variable declarations in `dashboard.js` cause a fatal JavaScript syntax error upon page load, preventing all client-side event listeners from binding and leaving the source mode selector and panel switching inactive.

## What Changes

- **Fix Syntax Error in Client Dashboard Script**: Eliminate duplicate identifier declarations (`btnConnectGDrive` and `gdriveAuthBadge`) in `app/static/js/dashboard.js` so client scripts load and initialize cleanly.
- **Enforce Mutual Exclusivity for Source Panels**: Ensure selecting any automated source (YouTube, Direct Link, Google Drive, Local File, Local Folder) immediately hides the "Manual Format Mode" section (`#panelSourceManual`) and reveals the corresponding source input panel.
- **Seamless Link Input Experience**: When YouTube or other URL-based sources are selected, display the input field container and automatically autofocus the input element so the user can immediately paste/insert their URL.
- **Restore Manual Mode on Switchback**: When switching back to "Manual Upload", ensure "Manual Format Mode" and the appropriate video or transcript dropzone reappear properly.
- **Client Script & UI Validation**: Introduce automated test coverage verifying clean script syntax, correct panel visibility toggling, and proper mutual exclusivity across all 6 source options.

## Capabilities

### New Capabilities
- `media-retrieval`: Multi-source dashboard selection, mutual exclusivity between manual format mode and automated content sources (YouTube, Direct Link, Google Drive, Local File, Local Folder), and fault-tolerant client-side event binding.

### Modified Capabilities

## Impact

- Affected Code:
  - `app/static/js/dashboard.js`: Resolve duplicate variable declarations and streamline source mode switching logic.
  - `app/templates/dashboard.html`: Verify radio/label element IDs and bindings for accessibility and click responsiveness.
  - `tests/test_source_mode_ui.py`: New or updated tests verifying client script syntax and source panel DOM structure.
- Breaking Changes: None. Backward compatibility with existing video/transcript uploads and backend ingestion endpoints is preserved.

