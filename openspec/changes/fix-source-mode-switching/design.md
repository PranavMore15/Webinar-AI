# Design

## Context

The WebinarAI dashboard allows users to ingest webinar materials either through manual upload (video MP4 or transcript TXT/VTT) or via automated sources (Direct Media Link, YouTube, Google Drive, Local File, Local Folder). 

In `app/templates/dashboard.html`, the content source selector contains 6 radio options with corresponding panels:
- `#panelSourceManual` contains the "Manual Format Mode" selector (`webinarSourceType`) and dropzone containers.
- `#panelSourceDirect`, `#panelSourceYouTube`, `#panelSourceGDrive`, `#panelSourceLocalFile`, `#panelSourceLocalFolder` represent the automated sources.

In `app/static/js/dashboard.js`, elements `btnConnectGDrive` and `gdriveAuthBadge` were declared twice using `const` within the same `DOMContentLoaded` callback scope (lines 66-67 and lines 351-352). This triggers an uncaught JavaScript `SyntaxError: Identifier 'btnConnectGDrive' has already been declared` upon page load, immediately halting script execution. Consequently:
1. No event listeners are attached to the source mode radio buttons or accessibility buttons.
2. Clicking the YouTube icon or any additional source does nothing.
3. The initial `#panelSourceManual` remains persistently visible because `switchContentSourceMode()` never executes.

## Goals / Non-Goals

**Goals:**
- Eliminate JavaScript syntax errors in `dashboard.js` by cleaning up duplicate identifier declarations.
- Ensure that selecting any automated source (YouTube, Direct Link, Google Drive, Local File, Local Folder) immediately hides the "Manual Format Mode" section (`#panelSourceManual`) and reveals the target source panel.
- Provide immediate input focus on URL inputs (such as `#youtubeUrlInput`) upon selecting link-based sources so users can immediately paste or enter links.
- Preserve proper state restoration when switching back to "Manual Upload".
- Add automated verification tests for client JavaScript syntax and template source structure.

**Non-Goals:**
- Modifying backend ingestion endpoints or provider implementations (`app/providers/`, `app/routes/`).
- Changing Section B (CSV upload, recipient validation) or processing pipeline triggering.

## Decisions

### 1. Identifier Scope Cleanup
Remove duplicate `const btnConnectGDrive` and `const gdriveAuthBadge` statements in `dashboard.js` and reuse the scoped constants initialized at lines 66-67.
- *Rationale*: Cleanest and most maintainable resolution conforming to the file's existing architecture.
- *Alternative Considered*: Wrapping Google Drive logic in an IIFE. Rejected as unnecessary overhead and inconsistent with neighboring provider handler patterns.

### 2. Panel Switching and Autofocus Logic in `switchContentSourceMode`
Update `switchContentSourceMode(mode)` to:
- Iterate through all registered `sourcePanels`: add class `d-none` to inactive panels and remove `d-none` from the active panel.
- When `mode !== 'manual'`, verify `#panelSourceManual` is hidden.
- If switching to `youtube`, invoke `youtubeUrlInput.focus()`.
- If switching to `direct`, invoke `directMediaUrlInput.focus()`.
- If switching to `gdrive`, invoke `gdriveUrlInput.focus()`.
- If switching to `manual`, invoke `updateWebinarSourceView()` to display the appropriate dropzone.
- Clear any previous error alerts (`hideWebinarError()`).

### 3. Automated Script Syntax & UI Testing
Create or update tests in `tests/test_source_mode_ui.py`:
- Use `node --check` via Python `subprocess` (or fallback AST verification) to ensure `app/static/js/dashboard.js` parses cleanly with zero syntax errors.
- Test dashboard HTML template rendering to confirm all 6 source radio buttons, labels, and panel IDs are present with correct attributes.

## Risks / Trade-offs

- **[Risk]** Browser cache may hold previous `dashboard.js`.
  → *Mitigation*: Ensure developers/users perform a hard refresh (`Ctrl+F5`) and verify script integrity via automated tests.
- **[Risk]** Clicking icon elements (`<i class="bi bi-youtube">`) inside labels might not propagate properly in custom browser webviews.
  → *Mitigation*: The HTML already uses Bootstrap's standard `<input type="radio" class="btn-check" id="modeYouTube">` and `<label for="modeYouTube">` which natively forwards clicks to the input element.

