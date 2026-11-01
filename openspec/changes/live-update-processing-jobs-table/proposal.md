# Proposal

## Why

When users initiate webinar processing from the dashboard submission modal (`#triggerConfirmModal`), closing the modal ("Close" button or backdrop/dismiss) leaves the homepage Section C ("Registered Processing Jobs (MySQL Persisted)") unchanged without displaying the currently processing job. The new job only appears in the dashboard table much later if the user refreshes after processing completes.

This disconnect occurs because submitting a job via `/api/submit-job` initiates background asynchronous processing and renders progress strictly within the modal, without dynamically prepending the new job row to the Section C table, hiding the empty state container when previous jobs were zero, or providing complete job row attributes in the background active-status polling endpoint (`/api/jobs/active-statuses`). Immediate table insertion and real-time live synchronization ensure users can safely close the modal at any time while retaining complete, transparent visibility into their in-progress jobs on the homepage.

## What Changes

- **Immediate Client Table Insertion on Job Start**:
  - Update `app/static/js/dashboard.js` upon successful response from `/api/submit-job` to dynamically construct and prepend a new table row (`#job-row-<id>`) into the Registered Processing Jobs table (`#recentJobsContainer tbody`).
  - Automatically transition the Section C view from `#jobEmptyState` to `#recentJobsContainer` if no previous jobs existed when the dashboard was loaded.
  - Increment the Section C job count badge counter.
  - Display active stage indicators (`Ready` / `Processing` with spinner) immediately.

- **Persistent Live Table Polling & Row Reconciliation**:
  - Enhance `initActiveJobsPolling` in `app/static/js/dashboard.js` to reconcile jobs returned from `/api/jobs/active-statuses`: if an active or recent job is returned by the server that does not yet exist in the DOM table, automatically render and prepend its row.
  - Ensure `updateJobTableRowFromData` smoothly transitions status badges, progress indicators, action buttons (e.g., Download PDF, Send Emails), and error states for newly inserted rows whether the submission modal is open or closed.

- **Complete Job Metadata in Active Statuses API**:
  - Expand `/api/jobs/active-statuses` in `app/routes/dashboard_routes.py` to return complete job presentation fields: `input_type`, `input_file_name`, `total_recipients`, and formatted `created_at` in addition to existing pipeline stage statuses.

- **Dashboard Template Active Status Consistency**:
  - Update `app/templates/dashboard.html` to treat `ready` as an active processing state alongside `transcribing`, `summarizing`, `generating_pdf`, `sending_emails`, and `processing`, rendering an animated spinner badge rather than a static pending badge if a page refresh occurs immediately after submission.

## Capabilities

### New Capabilities
- `dashboard-job-monitor`: Real-time tracking and dynamic rendering of registered processing jobs on the dashboard homepage table across all lifecycle stages (`ready`, `processing`, `transcribing`, `summarizing`, `generating_pdf`, `sending_emails`, `completed`, `partially_sent`, `failed`), supporting modal closure and asynchronous multi-job monitoring.

### Modified Capabilities
None.

## Impact
- **Backend**: `app/routes/dashboard_routes.py` (`/api/jobs/active-statuses` endpoint response payload).
- **Frontend**: `app/static/js/dashboard.js` (job submission handler, table row rendering/reconciliation, active jobs polling), `app/templates/dashboard.html` (job row template/table empty state container and status badges).
- **Dependencies & APIs**: No external dependencies added; uses existing Bootstrap 5, MySQL/SQLAlchemy models, and Flask routing.

