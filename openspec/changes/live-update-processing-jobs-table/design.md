# Design

## Context

When a user initiates video processing, `btnConfirmSubmitJob` in `app/static/js/dashboard.js` sends a POST request to `/api/submit-job`. The endpoint creates a `ProcessingJob` in MySQL with `overall_status = 'ready'`, spins up an asynchronous background pipeline worker, and returns JSON containing the new job record.

Currently, the client only reveals the internal progress bar in `#triggerConfirmModal` and starts polling `/api/jobs/<id>/status`. It never modifies the Section C table on the homepage. If the user dismisses the modal ("Close" button or backdrop), the homepage table continues to display whatever static list was rendered at initial page load. Furthermore:
1. If the user had zero previous jobs, the table (`#recentJobsContainer`) is completely absent from the DOM; only `#jobEmptyState` is rendered.
2. Background polling (`initActiveJobsPolling`) polls `/api/jobs/active-statuses` every 3 seconds, but ignores jobs that lack an existing `#job-row-<id>` element, and `/api/jobs/active-statuses` omits `input_type`, `input_file_name`, and `created_at`.
3. In `app/templates/dashboard.html`, the status `'ready'` is rendered with a static grey badge rather than an active processing spinner.

## Goals / Non-Goals

**Goals:**
- Provide instant visual confirmation of the newly created job in the Registered Processing Jobs table as soon as submission succeeds.
- Allow users to close the modal window immediately while retaining live visibility and real-time updates for the in-progress job in Section C.
- Automatically transition from the empty state view to the active table view when a job is submitted with no prior jobs.
- Enrich `/api/jobs/active-statuses` so client polling can reconcile and auto-insert missing jobs dynamically.
- Standardize `'ready'` as an active in-progress state across Jinja templates and JavaScript handlers.

**Non-Goals:**
- Modifying the underlying asynchronous pipeline execution in `pipeline_service.py` or database schemas.
- Altering the modal's internal progress bar, step cards, or completion alerts.
- Changing authentication or job access control policies.

## Decisions

### Decision 1: DOM Row Generation Function in `dashboard.js`
- **Approach**: Implement a dedicated `renderJobRow(job)` helper in `dashboard.js` that outputs the standard table row matching `app/templates/dashboard.html` with full attributes, status badges, and action buttons.
- **Rationale**: Immediate client-side rendering gives instant feedback (<10ms) without waiting for a server round-trip or template render endpoint.
- **Alternative considered**: Full page reload on modal submit or modal close. Rejected because full reloads disrupt user experience, lose modal states, and cause noticeable UI flicker.

### Decision 2: Empty State Container Handling
- **Approach**: Ensure `dashboard.html` renders the table container `#recentJobsContainer` (hidden with `d-none` when `recent_jobs` is empty) alongside `#jobEmptyState`, or render a dynamic table container in JavaScript if missing.
- **Rationale**: Having a pre-structured table template or dynamic fallback guarantees that inserting a row on an empty dashboard works flawlessly without server-side re-rendering.
- **Alternative considered**: Requiring at least one job to be present. Rejected because new users starting their first job would still experience the bug.

### Decision 3: Extended `/api/jobs/active-statuses` Payload
- **Approach**: Include `input_type`, `input_file_name`, `total_recipients`, and `created_at` in the dictionary returned by `get_active_job_statuses()` in `app/routes/dashboard_routes.py`.
- **Rationale**: Enables client-side background polling (`initActiveJobsPolling`) to detect and prepend jobs started in other tabs or jobs created prior to a client-side navigation.
- **Alternative considered**: Fetching individual job details via `/api/jobs/<id>` whenever an unrendered job ID is encountered. Rejected because it multiplies HTTP requests needlessly.

### Decision 4: Idempotent Prepending with Duplicate Guard
- **Approach**: In `prependJobRow(job)`, check `if (document.getElementById('job-row-' + job.id)) return;` before prepending to the table body.
- **Rationale**: Prevents race conditions between immediate submission callback insertion and background polling reconciliation.

## Risks / Trade-offs

- **[Risk] DOM Synchronization Mismatch**: Dynamic JavaScript row markup could drift from Jinja server-rendered markup.
  → *Mitigation*: Strictly align classes, element IDs (`job-row-<id>`, `job-status-cell-<id>`, `job-pdf-cell-<id>`, `job-email-cell-<id>`), badges, and icon structures between `dashboard.html` and `dashboard.js`.
- **[Risk] Badge Counter Drift**: Prepending rows could cause job count badges to desynchronize.
  → *Mitigation*: Update the table header counter badge text (e.g. `X Jobs`) when inserting a new unique row.

