# Tasks

## 1. Fix Client Script Syntax and Panel Switching

- [x] 1.1 Remove duplicate identifier declarations (`btnConnectGDrive`, `gdriveAuthBadge`) in `app/static/js/dashboard.js` and verify using `node --check app/static/js/dashboard.js` that the script parses cleanly without syntax errors
- [x] 1.2 Enhance `switchContentSourceMode` in `app/static/js/dashboard.js` to ensure `#panelSourceManual` (Manual Format Mode) is hidden when any automated source is active, and add automatic focus on the corresponding URL input (e.g., `#youtubeUrlInput` for YouTube)
- [x] 1.3 Ensure content source mode radio inputs and label cards in `app/templates/dashboard.html` consistently bind click and change events across all 6 source options

## 2. Automated UI and Integration Verification

- [x] 2.1 Implement `tests/test_dashboard_ui.py` with automated script syntax validation verifying `dashboard.js` compiles without errors
- [x] 2.2 Add template rendering tests in `tests/test_dashboard_ui.py` validating that Section A renders all 6 source options, `#panelSourceManual`, `#panelSourceYouTube`, and input controls
- [x] 2.3 Execute the full test suite (`pytest`) to verify all existing and new tests pass without regressions

