# Tasks

## 1. Backend Active Statuses API Enhancement

- [x] 1.1 Update `get_active_job_statuses()` in `app/routes/dashboard_routes.py` to include `input_type`, `input_file_name`, `total_recipients`, and formatted `created_at` in each job entry, and verify with pytest.
- [x] 1.2 Add tests to `tests/test_dashboard_routes.py` verifying `/api/jobs/active-statuses` returns complete job metadata fields.

## 2. Dashboard Template & Empty State Alignment

- [x] 2.1 Update `app/templates/dashboard.html` to treat `ready` as an active processing state rendering an animated spinner badge.
- [x] 2.2 Refactor `#jobEmptyState` and `#recentJobsContainer` in `app/templates/dashboard.html` so the table container is present in the DOM (toggled with `d-none` when empty) and accessible for dynamic row insertion.

## 3. Client-Side Live Table Synchronization

- [x] 3.1 Implement `renderJobRowHtml(job)` and `prependJobToTable(job)` helpers in `app/static/js/dashboard.js` with duplicate row guards, table count badge incrementing, and empty state toggling.
- [x] 3.2 Hook `prependJobToTable(result.job)` into the `/api/submit-job` success handler in `app/static/js/dashboard.js` so newly created jobs immediately appear in the table before modal closure.
- [x] 3.3 Enhance `initActiveJobsPolling()` in `app/static/js/dashboard.js` to detect any active job returned from `/api/jobs/active-statuses` missing from the DOM table and insert it automatically.

## 4. Integration Verification

- [ ] 4.1 Run the project test suite (`pytest tests/`) and verify all tests pass without regressions.
- [ ] 4.2 Perform an end-to-end integration check simulating job creation and polling to verify status transitions and persistence after modal dismissal.

