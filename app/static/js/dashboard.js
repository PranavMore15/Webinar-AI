// WebinarAI Dashboard Interactivity Script
// Client-side state orchestration for Media Upload, CSV Validation, and Processing Submissions

document.addEventListener('DOMContentLoaded', function () {
    // State management
    const state = {
        webinarSourceType: 'video', // 'video' or 'transcript'
        webinarUpload: null,        // Server-verified webinar metadata
        webinarFile: null,          // Client File object
        csvFile: null,              // Client CSV File object
        csvData: null               // Server-verified CSV validation breakdown
    };

    // Helper: Escape HTML to avoid XSS
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Helper: Format bytes
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // DOM Elements - Section A (Webinar Content)
    const radioVideo = document.getElementById('sourceTypeVideo');
    const radioTranscript = document.getElementById('sourceTypeTranscript');
    const videoUploadContainer = document.getElementById('videoUploadContainer');
    const transcriptUploadContainer = document.getElementById('transcriptUploadContainer');
    const videoFileInput = document.getElementById('videoFileInput');
    const transcriptFileInput = document.getElementById('transcriptFileInput');
    const webinarLoadingSpinner = document.getElementById('webinarLoadingSpinner');
    const webinarErrorAlert = document.getElementById('webinarErrorAlert');
    const webinarErrorTitle = document.getElementById('webinarErrorTitle');
    const webinarErrorMessage = document.getElementById('webinarErrorMessage');
    const webinarFileDetails = document.getElementById('webinarFileDetails');
    const webinarFileName = document.getElementById('webinarFileName');
    const webinarFileSize = document.getElementById('webinarFileSize');
    const webinarFileTypeBadge = document.getElementById('webinarFileTypeBadge');
    const webinarFileIcon = document.getElementById('webinarFileIcon');
    const btnRemoveWebinarFile = document.getElementById('btnRemoveWebinarFile');
    const webinarStatusBadge = document.getElementById('webinarStatusBadge');

    // DOM Elements - Section B (CSV Upload & Manual Recipients)
    const csvFileInput = document.getElementById('csvFileInput');
    const csvLoadingSpinner = document.getElementById('csvLoadingSpinner');
    const csvErrorAlert = document.getElementById('csvErrorAlert');
    const csvErrorTitle = document.getElementById('csvErrorTitle');
    const csvErrorMessage = document.getElementById('csvErrorMessage');
    const csvFileDetails = document.getElementById('csvFileDetails');
    const csvFileName = document.getElementById('csvFileName');
    const csvFileSize = document.getElementById('csvFileSize');
    const btnRemoveCsvFile = document.getElementById('btnRemoveCsvFile');
    const csvStatusBadge = document.getElementById('csvStatusBadge');
    const csvValidationCard = document.getElementById('csvValidationCard');

    // Manual Recipient Entry Elements
    const manualEmailInput = document.getElementById('manualEmailInput');
    const manualNameInput = document.getElementById('manualNameInput');
    const btnAddManualRecipient = document.getElementById('btnAddManualRecipient');
    const manualEmailAlert = document.getElementById('manualEmailAlert');
    const manualAlertIcon = document.getElementById('manualAlertIcon');
    const manualAlertMessage = document.getElementById('manualAlertMessage');
    const btnClearAllRecipients = document.getElementById('btnClearAllRecipients');
    const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

    // Statistics Counters
    const statTotalRows = document.getElementById('statTotalRows');
    const statValidRows = document.getElementById('statValidRows');
    const statDuplicateRows = document.getElementById('statDuplicateRows');
    const statInvalidRows = document.getElementById('statInvalidRows');
    const statBlankRows = document.getElementById('statBlankRows');

    // Tabs & Preview Tables
    const tabCountValid = document.getElementById('tabCountValid');
    const tabCountDuplicates = document.getElementById('tabCountDuplicates');
    const tabCountInvalid = document.getElementById('tabCountInvalid');
    const tableBodyValid = document.getElementById('tableBodyValid');
    const tableBodyDuplicates = document.getElementById('tableBodyDuplicates');
    const tableBodyInvalid = document.getElementById('tableBodyInvalid');
    const btnToggleCsvTable = document.getElementById('btnToggleCsvTable');
    const toggleTableText = document.getElementById('toggleTableText');
    const csvPreviewTableContainer = document.getElementById('csvPreviewTableContainer');

    // DOM Elements - Action Area
    const badgePrereqWebinar = document.getElementById('badgePrereqWebinar');
    const badgePrereqCsv = document.getElementById('badgePrereqCsv');
    const btnStartProcessing = document.getElementById('btnStartProcessing');

    // Modal elements
    const triggerConfirmModal = new bootstrap.Modal(document.getElementById('triggerConfirmModal'));
    const modalWebinarName = document.getElementById('modalWebinarName');
    const modalWebinarType = document.getElementById('modalWebinarType');
    const modalRecipientCount = document.getElementById('modalRecipientCount');
    const btnConfirmSubmitJob = document.getElementById('btnConfirmSubmitJob');
    const btnReloadDashboard = document.getElementById('btnReloadDashboard');
    const btnCloseModal = document.getElementById('btnCloseModal');
    const modalJobSuccessAlert = document.getElementById('modalJobSuccessAlert');
    const modalSuccessTitle = document.getElementById('modalSuccessTitle');
    const modalSuccessMessage = document.getElementById('modalSuccessMessage');
    const modalJobErrorAlert = document.getElementById('modalJobErrorAlert');
    const modalErrorMessage = document.getElementById('modalErrorMessage');
    const modalSubmissionExplainer = document.getElementById('modalSubmissionExplainer');

    // Modal Live Progress Stepper Elements
    const modalProcessingProgress = document.getElementById('modalProcessingProgress');
    const modalProgressBar = document.getElementById('modalProgressBar');
    const progressSpinner = document.getElementById('progressSpinner');
    const progressCurrentStage = document.getElementById('progressCurrentStage');
    const progressPercentageBadge = document.getElementById('progressPercentageBadge');
    const stepCardTranscript = document.getElementById('stepCardTranscript');
    const stepCardSummary = document.getElementById('stepCardSummary');
    const stepCardPdf = document.getElementById('stepCardPdf');
    const stepCardEmail = document.getElementById('stepCardEmail');
    const stepIconTranscript = document.getElementById('stepIconTranscript');
    const stepIconSummary = document.getElementById('stepIconSummary');
    const stepIconPdf = document.getElementById('stepIconPdf');
    const stepIconEmail = document.getElementById('stepIconEmail');
    const modalCompletionActions = document.getElementById('modalCompletionActions');
    const btnModalDownloadPdf = document.getElementById('btnModalDownloadPdf');

    // -------------------------------------------------------------------------
    // 1. Mutually Exclusive Webinar Input Switch
    // -------------------------------------------------------------------------
    async function updateWebinarSourceView() {
        if (radioVideo.checked) {
            state.webinarSourceType = 'video';
            videoUploadContainer.classList.remove('d-none');
            transcriptUploadContainer.classList.add('d-none');
            // If active file is not MP4, clear it
            if (state.webinarUpload && state.webinarUpload.input_type !== 'video') {
                await clearWebinarFile();
            }
        } else {
            state.webinarSourceType = 'transcript';
            videoUploadContainer.classList.add('d-none');
            transcriptUploadContainer.classList.remove('d-none');
            // If active file is video, clear it
            if (state.webinarUpload && state.webinarUpload.input_type !== 'transcript') {
                await clearWebinarFile();
            }
        }
    }

    radioVideo.addEventListener('change', updateWebinarSourceView);
    radioTranscript.addEventListener('change', updateWebinarSourceView);

    // -------------------------------------------------------------------------
    // 2. Webinar Media Upload & Validation Pipeline
    // -------------------------------------------------------------------------
    function showWebinarError(title, message) {
        if (webinarErrorTitle) webinarErrorTitle.textContent = title;
        if (webinarErrorMessage) webinarErrorMessage.textContent = message;
        if (webinarErrorAlert) webinarErrorAlert.classList.remove('d-none');
    }

    function hideWebinarError() {
        if (webinarErrorAlert) webinarErrorAlert.classList.add('d-none');
    }

    function clearWebinarClientState() {
        state.webinarUpload = null;
        state.webinarFile = null;
        videoFileInput.value = '';
        transcriptFileInput.value = '';
        webinarFileDetails.classList.add('d-none');
        webinarStatusBadge.className = 'badge bg-secondary-subtle text-secondary rounded-pill px-3 py-1';
        webinarStatusBadge.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Pending Input`;
    }

    async function clearWebinarFile() {
        clearWebinarClientState();
        hideWebinarError();

        // Notify server to delete file from disk storage and clear session
        try {
            await fetch('/api/clear-webinar', { method: 'POST' });
        } catch (e) {
            console.error('Failed to clear webinar on server:', e);
        }

        updatePrerequisites();
    }

    async function handleWebinarFileSelected(file) {
        if (!file) return;

        const ext = file.name.split('.').pop().toLowerCase();
        if (state.webinarSourceType === 'video' && ext !== 'mp4') {
            showWebinarError('Invalid Video Extension', "Please select a valid MP4 video file (.mp4).");
            videoFileInput.value = '';
            return;
        }
        if (state.webinarSourceType === 'transcript' && ext !== 'txt' && ext !== 'vtt') {
            showWebinarError('Invalid Transcript Extension', "Please select a valid TXT (.txt) or WebVTT (.vtt) file.");
            transcriptFileInput.value = '';
            return;
        }

        // Show uploading state
        hideWebinarError();
        webinarFileDetails.classList.add('d-none');
        webinarLoadingSpinner.classList.remove('d-none');
        webinarStatusBadge.className = 'badge bg-warning-subtle text-warning-emphasis rounded-pill px-3 py-1';
        webinarStatusBadge.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Uploading & Verifying...`;

        // Dispatch multipart upload to server
        const formData = new FormData();
        formData.append('file', file);
        formData.append('source_type', state.webinarSourceType);

        try {
            const response = await fetch('/api/upload-webinar', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            webinarLoadingSpinner.classList.add('d-none');

            if (!response.ok || !result.success) {
                showWebinarError('Validation Rejected', result.message || 'Webinar media validation failed on server.');
                clearWebinarClientState();
                webinarStatusBadge.className = 'badge bg-danger-subtle text-danger rounded-pill px-3 py-1';
                webinarStatusBadge.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> Upload Rejected`;
                updatePrerequisites();
                return;
            }

            // Success
            state.webinarUpload = result.details;
            state.webinarFile = file;

            // Render file info
            renderWebinarUploadSuccess(result.details);
            updatePrerequisites();

        } catch (error) {
            webinarLoadingSpinner.classList.add('d-none');
            showWebinarError('Network / Upload Error', 'An unexpected error occurred while uploading media: ' + error.message);
            clearWebinarClientState();
            webinarStatusBadge.className = 'badge bg-danger-subtle text-danger rounded-pill px-3 py-1';
            webinarStatusBadge.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> Upload Error`;
            updatePrerequisites();
        }
    }

    function renderWebinarUploadSuccess(details) {
        webinarFileName.textContent = details.original_filename;
        webinarFileSize.textContent = formatBytes(details.file_size);
        const ext = (details.file_extension || '').toUpperCase();
        webinarFileTypeBadge.textContent = ext;

        if (details.input_type === 'video') {
            webinarFileIcon.className = 'bi bi-file-earmark-play fs-4 text-primary';
        } else {
            webinarFileIcon.className = 'bi bi-file-earmark-text fs-4 text-info';
        }

        webinarFileDetails.classList.remove('d-none');
        webinarStatusBadge.className = 'badge bg-success-subtle text-success rounded-pill px-3 py-1';
        webinarStatusBadge.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Ready (${ext})`;
    }

    videoFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleWebinarFileSelected(e.target.files[0]);
    });

    transcriptFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleWebinarFileSelected(e.target.files[0]);
    });

    btnRemoveWebinarFile.addEventListener('click', clearWebinarFile);

    // -------------------------------------------------------------------------
    // 3. Backend CSV Upload & Validation Pipeline
    // -------------------------------------------------------------------------
    function showCsvError(title, message) {
        csvErrorTitle.textContent = title;
        csvErrorMessage.textContent = message;
        csvErrorAlert.classList.remove('d-none');
    }

    function hideCsvError() {
        csvErrorAlert.classList.add('d-none');
    }

    function clearCsvClientState() {
        state.csvFile = null;
        state.csvData = null;
        csvFileInput.value = '';
        if (manualEmailInput) manualEmailInput.value = '';
        if (manualNameInput) manualNameInput.value = '';
        hideManualAlert();
        csvFileDetails.classList.add('d-none');
        csvValidationCard.classList.add('d-none');
    }

    async function handleClearCsv() {
        clearCsvClientState();
        hideCsvError();
        csvStatusBadge.className = 'badge bg-secondary-subtle text-secondary rounded-pill px-3 py-1';
        csvStatusBadge.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Pending Recipients`;

        // Clear backend session state
        try {
            await fetch('/api/clear-csv', { method: 'POST' });
        } catch (e) {
            console.error('Failed to notify server of recipient clear:', e);
        }

        updatePrerequisites();
    }

    function showManualAlert(message, isError = true) {
        if (!manualEmailAlert) return;
        manualEmailAlert.className = `alert ${isError ? 'alert-danger' : 'alert-success'} border-0 mt-2 mb-0 py-2 small shadow-sm rounded-3`;
        if (manualAlertIcon) {
            manualAlertIcon.className = `bi ${isError ? 'bi-exclamation-triangle-fill' : 'bi-check-circle-fill'} me-1`;
        }
        if (manualAlertMessage) {
            manualAlertMessage.textContent = message;
        }
        manualEmailAlert.classList.remove('d-none');
    }

    function hideManualAlert() {
        if (manualEmailAlert) manualEmailAlert.classList.add('d-none');
    }

    async function handleAddManualRecipient() {
        hideManualAlert();
        const rawEmail = manualEmailInput ? manualEmailInput.value.trim() : '';
        const rawName = manualNameInput ? manualNameInput.value.trim() : '';

        if (!rawEmail) {
            showManualAlert('Email address is required.', true);
            if (manualEmailInput) manualEmailInput.focus();
            return;
        }

        if (!EMAIL_REGEX.test(rawEmail)) {
            showManualAlert('Please enter a valid email address (e.g., student@university.edu).', true);
            if (manualEmailInput) manualEmailInput.focus();
            return;
        }

        if (btnAddManualRecipient) {
            btnAddManualRecipient.disabled = true;
            btnAddManualRecipient.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';
        }

        try {
            const response = await fetch('/api/recipients/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: rawEmail, name: rawName })
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                showManualAlert(result.message || 'Failed to add recipient.', true);
                return;
            }

            manualEmailInput.value = '';
            manualNameInput.value = '';
            showManualAlert(result.message || 'Recipient added successfully.', false);

            if (!state.csvData) {
                state.csvData = {
                    filename: 'Manual Entry',
                    total_data_rows: result.valid_unique_count,
                    valid_unique_count: result.valid_unique_count,
                    duplicate_count: 0,
                    invalid_count: 0,
                    blank_count: 0,
                    valid_recipients: result.recipients,
                    duplicate_rows: [],
                    invalid_rows: []
                };
            } else {
                state.csvData.valid_unique_count = result.valid_unique_count;
                state.csvData.valid_recipients = result.recipients;
                state.csvData.total_data_rows = Math.max(state.csvData.total_data_rows || 0, result.valid_unique_count);
            }

            renderCsvStats(state.csvData);
            updatePrerequisites();

        } catch (err) {
            showManualAlert('Network / Server Error: ' + err.message, true);
        } finally {
            if (btnAddManualRecipient) {
                btnAddManualRecipient.disabled = false;
                btnAddManualRecipient.innerHTML = '<i class="bi bi-plus-lg"></i> <span>Add</span>';
            }
        }
    }

    async function handleRemoveRecipient(email) {
        if (!email) return;

        try {
            const response = await fetch('/api/recipients/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email })
            });

            const result = await response.json();
            if (!response.ok || !result.success) {
                alert(result.message || 'Failed to remove recipient.');
                return;
            }

            if (state.csvData) {
                state.csvData.valid_unique_count = result.valid_unique_count;
                state.csvData.valid_recipients = result.recipients;
                if (result.valid_unique_count === 0 && (!state.csvData.duplicate_rows || state.csvData.duplicate_rows.length === 0) && (!state.csvData.invalid_rows || state.csvData.invalid_rows.length === 0)) {
                    clearCsvClientState();
                    csvStatusBadge.className = 'badge bg-secondary-subtle text-secondary rounded-pill px-3 py-1';
                    csvStatusBadge.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Pending Recipients`;
                } else {
                    renderCsvStats(state.csvData);
                }
            }

            updatePrerequisites();
        } catch (err) {
            alert('Error removing recipient: ' + err.message);
        }
    }

    async function handleCsvFileSelected(file) {
        if (!file) return;

        // Preliminary client extension check
        if (!file.name.toLowerCase().endsWith('.csv')) {
            showCsvError('Invalid File Extension', 'Please select a valid .csv spreadsheet file.');
            csvFileInput.value = '';
            return;
        }

        // Show loading state
        hideCsvError();
        csvFileDetails.classList.add('d-none');
        csvValidationCard.classList.add('d-none');
        csvLoadingSpinner.classList.remove('d-none');
        csvStatusBadge.className = 'badge bg-warning-subtle text-warning-emphasis rounded-pill px-3 py-1';
        csvStatusBadge.innerHTML = `<i class="bi bi-hourglass-split me-1"></i> Validating on server...`;

        // Create form data and dispatch to backend validation endpoint
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/upload-csv', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            csvLoadingSpinner.classList.add('d-none');

            if (!response.ok || !result.success) {
                // Validation rejection from server
                showCsvError('Validation Rejected', result.message || 'CSV validation failed on server.');
                clearCsvClientState();
                csvStatusBadge.className = 'badge bg-danger-subtle text-danger rounded-pill px-3 py-1';
                csvStatusBadge.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> Invalid CSV`;
                updatePrerequisites();
                return;
            }

            // Validation succeeded
            state.csvFile = file;
            state.csvData = result;

            // Update file details
            csvFileName.textContent = result.filename || file.name;
            csvFileSize.textContent = formatBytes(file.size);
            csvFileDetails.classList.remove('d-none');

            // Render stats
            renderCsvStats(result);
            updatePrerequisites();

        } catch (error) {
            csvLoadingSpinner.classList.add('d-none');
            showCsvError('Network / Server Error', 'An unexpected error occurred while validating the CSV: ' + error.message);
            clearCsvClientState();
            csvStatusBadge.className = 'badge bg-danger-subtle text-danger rounded-pill px-3 py-1';
            csvStatusBadge.innerHTML = `<i class="bi bi-exclamation-triangle-fill me-1"></i> Validation Error`;
            updatePrerequisites();
        }
    }

    function renderCsvStats(result) {
        statTotalRows.textContent = result.total_data_rows || (result.valid_unique_count || 0);
        statValidRows.textContent = result.valid_unique_count || 0;
        statDuplicateRows.textContent = result.duplicate_count || 0;
        statInvalidRows.textContent = result.invalid_count || 0;
        statBlankRows.textContent = result.blank_count || 0;

        tabCountValid.textContent = result.valid_unique_count || 0;
        tabCountDuplicates.textContent = result.duplicate_count || 0;
        tabCountInvalid.textContent = (result.invalid_rows || []).length;

        // Render Valid Recipients table with Source and Delete controls
        tableBodyValid.innerHTML = '';
        if (!result.valid_recipients || result.valid_recipients.length === 0) {
            tableBodyValid.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">No valid recipient email addresses in active list.</td></tr>';
        } else {
            result.valid_recipients.forEach((item, index) => {
                const tr = document.createElement('tr');
                const sourceBadge = item.source === 'manual'
                    ? '<span class="badge bg-info-subtle text-info border border-info-subtle">Manual</span>'
                    : '<span class="badge bg-secondary-subtle text-secondary border">CSV</span>';
                tr.innerHTML = `
                    <td class="text-muted">${item.row || (index + 1)}</td>
                    <td class="font-monospace fw-semibold text-success">${escapeHtml(item.original_email || item.email)}</td>
                    <td class="text-secondary">${escapeHtml(item.name || '—')}</td>
                    <td>${sourceBadge}</td>
                    <td class="text-center">
                        <button type="button" class="btn btn-sm btn-outline-danger border-0 py-0 px-1 btn-delete-recipient" data-email="${escapeHtml(item.email)}" title="Delete recipient">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                `;
                tableBodyValid.appendChild(tr);
            });

            // Attach click listeners to delete buttons
            tableBodyValid.querySelectorAll('.btn-delete-recipient').forEach(btn => {
                btn.addEventListener('click', () => {
                    const email = btn.getAttribute('data-email');
                    handleRemoveRecipient(email);
                });
            });
        }

        // Render Duplicates table
        tableBodyDuplicates.innerHTML = '';
        if (!result.duplicate_rows || result.duplicate_rows.length === 0) {
            tableBodyDuplicates.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-3">No duplicate email rows found.</td></tr>';
        } else {
            result.duplicate_rows.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="text-muted">${item.row}</td>
                    <td class="font-monospace text-warning-emphasis">${escapeHtml(item.email)}</td>
                    <td class="text-muted small">${escapeHtml(item.reason)}</td>
                `;
                tableBodyDuplicates.appendChild(tr);
            });
        }

        // Render Invalid / Blank table
        tableBodyInvalid.innerHTML = '';
        if (!result.invalid_rows || result.invalid_rows.length === 0) {
            tableBodyInvalid.innerHTML = '<tr><td colspan="3" class="text-center text-muted py-3">No invalid or blank email rows found.</td></tr>';
        } else {
            result.invalid_rows.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="text-muted">${item.row}</td>
                    <td class="font-monospace text-danger">${escapeHtml(item.email)}</td>
                    <td class="text-danger small">${escapeHtml(item.reason)}</td>
                `;
                tableBodyInvalid.appendChild(tr);
            });
        }

        csvValidationCard.classList.remove('d-none');

        // Status badge
        if (result.valid_unique_count > 0) {
            csvStatusBadge.className = 'badge bg-success-subtle text-success rounded-pill px-3 py-1';
            csvStatusBadge.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> ${result.valid_unique_count} Valid Recipient${result.valid_unique_count === 1 ? '' : 's'}`;
        } else {
            csvStatusBadge.className = 'badge bg-danger-subtle text-danger rounded-pill px-3 py-1';
            csvStatusBadge.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> 0 Valid Recipients`;
        }
    }

    csvFileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) handleCsvFileSelected(e.target.files[0]);
    });

    btnRemoveCsvFile.addEventListener('click', handleClearCsv);

    if (btnAddManualRecipient) {
        btnAddManualRecipient.addEventListener('click', handleAddManualRecipient);
    }

    if (manualEmailInput) {
        manualEmailInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleAddManualRecipient();
            }
        });
    }

    if (manualNameInput) {
        manualNameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleAddManualRecipient();
            }
        });
    }

    if (btnClearAllRecipients) {
        btnClearAllRecipients.addEventListener('click', handleClearCsv);
    }

    // Toggle Detailed Rows Container
    btnToggleCsvTable.addEventListener('click', () => {
        const isHidden = csvPreviewTableContainer.classList.contains('d-none');
        if (isHidden) {
            csvPreviewTableContainer.classList.remove('d-none');
            toggleTableText.textContent = 'Hide Detailed Rows';
            btnToggleCsvTable.querySelector('i').className = 'bi bi-chevron-up';
        } else {
            csvPreviewTableContainer.classList.add('d-none');
            toggleTableText.textContent = 'Show Detailed Rows';
            btnToggleCsvTable.querySelector('i').className = 'bi bi-chevron-down';
        }
    });

    // -------------------------------------------------------------------------
    // 4. Prerequisites & Dynamic Action Button Enabling
    // -------------------------------------------------------------------------
    function updatePrerequisites() {
        const hasWebinar = state.webinarUpload !== null;
        const hasRecipients = state.csvData !== null && state.csvData.valid_unique_count > 0;

        // Update Webinar Badge
        if (hasWebinar) {
            badgePrereqWebinar.className = 'badge bg-success-subtle text-success border border-success';
            badgePrereqWebinar.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Webinar Input (${escapeHtml(state.webinarUpload.original_filename)})`;
        } else {
            badgePrereqWebinar.className = 'badge text-bg-light border text-secondary';
            badgePrereqWebinar.innerHTML = `<i class="bi bi-circle me-1"></i> Webinar Input (Pending)`;
        }

        // Update CSV Badge
        if (hasRecipients) {
            badgePrereqCsv.className = 'badge bg-success-subtle text-success border border-success';
            badgePrereqCsv.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> ${state.csvData.valid_unique_count} Valid Recipient${state.csvData.valid_unique_count === 1 ? '' : 's'} (Server Verified)`;
        } else {
            badgePrereqCsv.className = 'badge text-bg-light border text-secondary';
            badgePrereqCsv.innerHTML = `<i class="bi bi-circle me-1"></i> Valid Recipients (Pending)`;
        }

        // Action button is enabled ONLY when both conditions are satisfied
        btnStartProcessing.disabled = !(hasWebinar && hasRecipients);
    }

    // -------------------------------------------------------------------------
    // 5. Main Action Button: Trigger Confirmation Modal
    // -------------------------------------------------------------------------
    btnStartProcessing.addEventListener('click', async function () {
        if (btnStartProcessing.disabled) return;

        // Reset modal states
        modalJobSuccessAlert.classList.add('d-none');
        modalJobErrorAlert.classList.add('d-none');
        modalSubmissionExplainer.classList.remove('d-none');
        modalProcessingProgress.classList.add('d-none');
        modalCompletionActions.classList.add('d-none');
        modalProgressBar.className = 'progress-bar progress-bar-striped progress-bar-animated bg-primary';
        modalProgressBar.style.width = '0%';
        progressPercentageBadge.textContent = '0%';
        progressPercentageBadge.className = 'badge bg-primary rounded-pill px-2.5 py-1';
        progressSpinner.classList.remove('d-none');
        resetStepCards();

        btnConfirmSubmitJob.classList.remove('d-none');
        btnConfirmSubmitJob.disabled = false;
        btnConfirmSubmitJob.innerHTML = `<i class="bi bi-play-fill fs-5"></i> Start Processing & Deliver Email`;
        btnReloadDashboard.classList.add('d-none');
        btnCloseModal.disabled = false;

        modalWebinarName.textContent = state.webinarUpload ? state.webinarUpload.original_filename : 'None';
        modalWebinarType.textContent = (state.webinarUpload ? state.webinarUpload.input_type : state.webinarSourceType).toUpperCase();
        modalRecipientCount.textContent = state.csvData ? state.csvData.valid_unique_count : 0;

        // Revalidate server-side state before presenting modal
        try {
            const response = await fetch('/api/validate-state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    hasWebinar: state.webinarUpload !== null,
                    webinarType: state.webinarSourceType,
                    webinarName: state.webinarUpload ? state.webinarUpload.original_filename : ''
                })
            });

            const result = await response.json();
            if (response.ok && result.success) {
                triggerConfirmModal.show();
            } else {
                alert('Server pre-validation rejected: ' + (result.message || 'Inputs are not ready on server.'));
            }
        } catch (err) {
            console.error('Validation verification error:', err);
            alert('Network error while verifying server-side state: ' + err.message);
        }
    });

    // -------------------------------------------------------------------------
    // 6. Live Progress Tracking & Modal Pipeline Polling
    // -------------------------------------------------------------------------
    let activePollInterval = null;

    function resetStepCards() {
        [stepCardTranscript, stepCardSummary, stepCardPdf, stepCardEmail].forEach(card => {
            if (card) card.className = 'p-2 rounded border bg-white';
        });
        if (stepIconTranscript) stepIconTranscript.className = 'bi bi-file-earmark-text d-block fs-6 text-muted mb-1';
        if (stepIconSummary) stepIconSummary.className = 'bi bi-stars d-block fs-6 text-muted mb-1';
        if (stepIconPdf) stepIconPdf.className = 'bi bi-file-earmark-pdf d-block fs-6 text-muted mb-1';
        if (stepIconEmail) stepIconEmail.className = 'bi bi-envelope-check d-block fs-6 text-muted mb-1';
    }

    function setStepStatus(card, icon, status) {
        if (!card || !icon) return;
        if (status === 'completed') {
            card.className = 'p-2 rounded border border-success bg-success-subtle text-success';
            icon.className = 'bi bi-check-circle-fill d-block fs-6 text-success mb-1';
        } else if (status === 'active') {
            card.className = 'p-2 rounded border border-primary bg-primary-subtle text-primary';
            icon.className = 'spinner-border spinner-border-sm text-primary d-inline-block mb-1';
        } else if (status === 'failed') {
            card.className = 'p-2 rounded border border-danger bg-danger-subtle text-danger';
            icon.className = 'bi bi-x-circle-fill d-block fs-6 text-danger mb-1';
        } else {
            card.className = 'p-2 rounded border bg-white text-muted';
        }
    }

    function updateJobTableRowFromData(job) {
        if (!job || !job.id) return;
        const row = document.getElementById(`job-row-${job.id}`);
        if (!row) return;

        // Status Cell
        const statusCell = document.getElementById(`job-status-cell-${job.id}`);
        if (statusCell) {
            if (job.overall_status === 'completed') {
                statusCell.innerHTML = `<span class="badge bg-success-subtle text-success border border-success-subtle"><i class="bi bi-check2-circle me-1"></i>Completed</span>`;
            } else if (['transcribing', 'summarizing', 'generating_pdf', 'sending_emails', 'processing', 'ready'].includes(job.overall_status)) {
                const label = job.overall_status.replace('_', ' ');
                const cap = label.charAt(0).toUpperCase() + label.slice(1);
                statusCell.innerHTML = `<span class="badge bg-primary-subtle text-primary border border-primary-subtle"><span class="spinner-border spinner-border-sm me-1" style="width: 0.72rem; height: 0.72rem;"></span>${escapeHtml(cap)}</span>`;
            } else if (job.overall_status === 'partially_sent') {
                statusCell.innerHTML = `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle"><i class="bi bi-exclamation-circle-fill me-1"></i>Partial</span>`;
            } else if (job.overall_status === 'failed') {
                statusCell.innerHTML = `<span class="badge bg-danger-subtle text-danger border border-danger-subtle" title="${escapeHtml(job.error_message || 'Failed')}"><i class="bi bi-x-circle-fill me-1"></i>Failed</span>`;
            }
        }

        // PDF Cell
        const pdfCell = document.getElementById(`job-pdf-cell-${job.id}`);
        if (pdfCell) {
            if (job.pdf_ready || (job.pdf_status === 'completed' && job.pdf_path)) {
                pdfCell.innerHTML = `<a href="/dashboard/jobs/${job.id}/download-pdf" class="btn btn-sm btn-outline-primary rounded-pill px-2.5 py-1 fw-semibold d-inline-flex align-items-center gap-1 shadow-xs" title="Download AI-Generated Summary PDF"><i class="bi bi-file-earmark-pdf-fill text-danger"></i><span>Download</span></a>`;
            } else if (job.summary_status === 'completed') {
                pdfCell.innerHTML = `<a href="/dashboard/jobs/${job.id}/download-pdf" class="btn btn-sm btn-outline-success rounded-pill px-2.5 py-1 small fw-semibold d-inline-flex align-items-center gap-1" title="Generate and Download PDF"><i class="bi bi-file-earmark-arrow-down-fill text-success"></i><span>Get PDF</span></a>`;
            } else if (job.pdf_status === 'generating') {
                pdfCell.innerHTML = `<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle rounded-pill px-2 py-1"><span class="spinner-border spinner-border-sm me-1" style="width: 0.75rem; height: 0.75rem;"></span> Generating</span>`;
            } else if (job.pdf_status === 'failed') {
                pdfCell.innerHTML = `<span class="badge bg-danger-subtle text-danger border border-danger-subtle rounded-pill px-2 py-1" title="${escapeHtml(job.error_message || 'PDF Generation Failed')}"><i class="bi bi-exclamation-triangle-fill me-1"></i> Failed</span>`;
            }
        }

        // Email Cell
        const emailCell = document.getElementById(`job-email-cell-${job.id}`);
        if (emailCell) {
            if (job.email_status === 'completed') {
                emailCell.innerHTML = `<div class="d-inline-flex align-items-center gap-1"><span class="badge bg-success-subtle text-success border border-success-subtle rounded-pill px-2 py-1" title="All emails sent successfully"><i class="bi bi-envelope-check-fill me-1"></i>Sent (${job.successful_emails})</span><button type="button" class="btn btn-sm btn-outline-secondary rounded-pill px-2 py-0.5 small" onclick="openDeliveryReportModal(${job.id})" title="View Delivery Audit Report"><i class="bi bi-file-text"></i></button></div>`;
            } else if (job.email_status === 'partially_sent') {
                emailCell.innerHTML = `<div class="d-inline-flex align-items-center gap-1"><span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle rounded-pill px-2 py-1" title="Partially sent"><i class="bi bi-exclamation-circle-fill me-1"></i>Partial (${job.successful_emails}/${job.total_recipients})</span><button type="button" class="btn btn-sm btn-outline-warning rounded-pill px-2 py-0.5 small fw-semibold" onclick="openEmailPreFlightModal(${job.id}, true)" title="Retry Failed Deliveries"><i class="bi bi-arrow-repeat me-1"></i>Retry</button><button type="button" class="btn btn-sm btn-outline-secondary rounded-pill px-2 py-0.5 small" onclick="openDeliveryReportModal(${job.id})" title="View Delivery Report"><i class="bi bi-file-text"></i></button></div>`;
            } else if (job.email_status === 'sending') {
                emailCell.innerHTML = `<span class="badge bg-primary-subtle text-primary border border-primary-subtle rounded-pill px-2 py-1"><span class="spinner-border spinner-border-sm me-1" style="width: 0.7rem; height: 0.7rem;"></span> Sending...</span>`;
            } else if (job.email_status === 'failed') {
                emailCell.innerHTML = `<div class="d-inline-flex align-items-center gap-1"><span class="badge bg-danger-subtle text-danger border border-danger-subtle rounded-pill px-2 py-1" title="Delivery failed"><i class="bi bi-x-circle-fill me-1"></i>Failed</span><button type="button" class="btn btn-sm btn-outline-danger rounded-pill px-2 py-0.5 small fw-semibold" onclick="openEmailPreFlightModal(${job.id}, true)" title="Retry Sending"><i class="bi bi-arrow-repeat me-1"></i>Retry</button><button type="button" class="btn btn-sm btn-outline-secondary rounded-pill px-2 py-0.5 small" onclick="openDeliveryReportModal(${job.id})" title="View Error Report"><i class="bi bi-file-text"></i></button></div>`;
            } else if (job.pdf_ready || (job.pdf_status === 'completed' && job.pdf_path)) {
                emailCell.innerHTML = `<button type="button" class="btn btn-sm btn-primary rounded-pill px-2.5 py-1 fw-semibold d-inline-flex align-items-center gap-1 shadow-xs" onclick="openEmailPreFlightModal(${job.id}, false)" title="Send Summary PDF to Validated Recipients"><i class="bi bi-send-fill text-white"></i><span>Send Emails</span></button>`;
            }
        }
    }

    function pollJobPipelineStatus(jobId) {
        if (activePollInterval) clearInterval(activePollInterval);

        activePollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/jobs/${jobId}/status`);
                if (!response.ok) return;

                const data = await response.json();
                if (!data.success || !data.job) return;

                const job = data.job;

                // Update percentage and label
                const percent = job.progress_percent || 10;
                modalProgressBar.style.width = percent + '%';
                progressPercentageBadge.textContent = percent + '%';
                progressCurrentStage.textContent = job.stage_label || 'Processing...';

                // Step 1: Ingest Media / Transcript
                if (job.transcript_status === 'completed') {
                    setStepStatus(stepCardTranscript, stepIconTranscript, 'completed');
                } else if (job.overall_status === 'transcribing') {
                    setStepStatus(stepCardTranscript, stepIconTranscript, 'active');
                } else if (job.transcript_status === 'failed') {
                    setStepStatus(stepCardTranscript, stepIconTranscript, 'failed');
                }

                // Step 2: AI Summarization
                if (job.summary_status === 'completed') {
                    setStepStatus(stepCardSummary, stepIconSummary, 'completed');
                } else if (job.overall_status === 'summarizing') {
                    setStepStatus(stepCardSummary, stepIconSummary, 'active');
                } else if (job.summary_status === 'failed') {
                    setStepStatus(stepCardSummary, stepIconSummary, 'failed');
                }

                // Step 3: PDF Generation
                if (job.pdf_status === 'completed') {
                    setStepStatus(stepCardPdf, stepIconPdf, 'completed');
                } else if (job.overall_status === 'generating_pdf') {
                    setStepStatus(stepCardPdf, stepIconPdf, 'active');
                } else if (job.pdf_status === 'failed') {
                    setStepStatus(stepCardPdf, stepIconPdf, 'failed');
                }

                // Step 4: Email Delivery
                if (job.email_status === 'completed') {
                    setStepStatus(stepCardEmail, stepIconEmail, 'completed');
                } else if (job.overall_status === 'sending_emails') {
                    setStepStatus(stepCardEmail, stepIconEmail, 'active');
                } else if (job.email_status === 'failed') {
                    setStepStatus(stepCardEmail, stepIconEmail, 'failed');
                }

                // Update table row concurrently
                updateJobTableRowFromData(job);

                // Terminal states
                if (job.overall_status === 'completed' || job.overall_status === 'partially_sent') {
                    clearInterval(activePollInterval);
                    activePollInterval = null;

                    modalProgressBar.className = 'progress-bar bg-success';
                    modalProgressBar.style.width = '100%';
                    progressPercentageBadge.textContent = '100%';
                    progressPercentageBadge.className = 'badge bg-success rounded-pill px-2.5 py-1';
                    progressSpinner.classList.add('d-none');

                    modalJobSuccessAlert.classList.remove('d-none');
                    modalSuccessTitle.textContent = 'Pipeline Completed & Emails Delivered!';
                    modalSuccessMessage.innerHTML = `Successfully processed <strong>${escapeHtml(job.input_file_name)}</strong> and emailed summary PDF to <strong>${job.successful_emails}</strong> recipient(s).`;

                    if (job.pdf_url) {
                        btnModalDownloadPdf.href = job.pdf_url;
                        modalCompletionActions.classList.remove('d-none');
                    }

                    btnReloadDashboard.classList.remove('d-none');

                } else if (job.overall_status === 'failed') {
                    clearInterval(activePollInterval);
                    activePollInterval = null;

                    modalProgressBar.className = 'progress-bar bg-danger';
                    progressPercentageBadge.className = 'badge bg-danger rounded-pill px-2.5 py-1';
                    progressSpinner.classList.add('d-none');

                    modalJobErrorAlert.classList.remove('d-none');
                    modalErrorTitle.textContent = 'Pipeline Execution Stopped';
                    modalErrorMessage.textContent = job.error_message || 'Processing encountered an error.';

                    btnReloadDashboard.classList.remove('d-none');
                }

            } catch (err) {
                console.error('Polling error:', err);
            }
        }, 1500);
    }

    // Modal Submit Trigger
    btnConfirmSubmitJob.addEventListener('click', async function () {
        btnConfirmSubmitJob.disabled = true;
        btnCloseModal.disabled = true;
        btnConfirmSubmitJob.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status"></span>Starting Automated Pipeline...`;

        try {
            const response = await fetch('/api/submit-job', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });

            const result = await response.json();

            if (response.ok && result.success) {
                // Job persisted in MySQL and async background worker started
                modalSubmissionExplainer.classList.add('d-none');
                btnConfirmSubmitJob.classList.add('d-none');
                btnCloseModal.disabled = false;

                // Clear temporary client form states since job was persisted
                clearWebinarClientState();
                clearCsvClientState();
                updatePrerequisites();

                // Show live progress card inside the modal!
                modalProcessingProgress.classList.remove('d-none');
                pollJobPipelineStatus(result.job.id);

            } else {
                btnConfirmSubmitJob.disabled = false;
                btnCloseModal.disabled = false;
                btnConfirmSubmitJob.innerHTML = `<i class="bi bi-play-fill fs-5"></i> Retry Submission`;

                modalErrorTitle.textContent = 'Job Creation Failed';
                modalErrorMessage.textContent = result.message || 'Database transaction error occurred.';
                modalJobErrorAlert.classList.remove('d-none');
            }
        } catch (err) {
            btnConfirmSubmitJob.disabled = false;
            btnCloseModal.disabled = false;
            btnConfirmSubmitJob.innerHTML = `<i class="bi bi-play-fill fs-5"></i> Retry Submission`;

            modalErrorTitle.textContent = 'Network / Server Error';
            modalErrorMessage.textContent = err.message;
            modalJobErrorAlert.classList.remove('d-none');
        }
    });

    // Background polling for Section C table
    function initActiveJobsPolling() {
        setInterval(async () => {
            try {
                const response = await fetch('/api/jobs/active-statuses');
                if (!response.ok) return;
                const data = await response.json();
                if (!data.success || !data.jobs) return;

                data.jobs.forEach(job => {
                    updateJobTableRowFromData(job);
                });
            } catch (err) {
                // Background poll failure is silent
            }
        }, 3000);
    }
    initActiveJobsPolling();

    // -------------------------------------------------------------------------
    // 7. Initial Bootstrap from Existing Active Session States
    // -------------------------------------------------------------------------
    if (window.INITIAL_WEBINAR_STATE) {
        state.webinarUpload = window.INITIAL_WEBINAR_STATE;
        state.webinarSourceType = window.INITIAL_WEBINAR_STATE.input_type || 'video';
        if (state.webinarSourceType === 'video') {
            radioVideo.checked = true;
        } else {
            radioTranscript.checked = true;
        }
        updateWebinarSourceView();
        renderWebinarUploadSuccess(window.INITIAL_WEBINAR_STATE);
    }

    if (window.INITIAL_CSV_STATE) {
        state.csvData = window.INITIAL_CSV_STATE;
        csvFileName.textContent = window.INITIAL_CSV_STATE.filename || 'recipients.csv';
        csvFileSize.textContent = 'Server Verified';
        csvFileDetails.classList.remove('d-none');
        renderCsvStats(window.INITIAL_CSV_STATE);
    }

    updatePrerequisites();
});

// =========================================================================
// 8. SMTP Email Delivery & Audit Report Controllers (Prompt 7)
// =========================================================================
(function () {
    let currentActiveJobId = null;
    let currentIsRetryMode = false;

    function safeEscapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    window.openEmailPreFlightModal = async function(jobId, isRetry) {
        currentActiveJobId = jobId;
        currentIsRetryMode = !!isRetry;

        const modalEl = document.getElementById('emailPreFlightModal');
        if (!modalEl) return;
        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

        // Reset UI state
        document.getElementById('emailModalActionTitle').textContent = isRetry ? 'Retry Summary PDF Delivery' : 'Send Summary PDF to Recipients';
        document.getElementById('btnConfirmSendText').textContent = isRetry ? 'Retry Delivery' : 'Confirm & Send Emails';
        document.getElementById('preFlightJobId').textContent = '#' + jobId;
        document.getElementById('preFlightFeedbackAlert').classList.add('d-none');
        document.getElementById('preFlightSmtpAlert').classList.add('d-none');
        const sendBtn = document.getElementById('btnConfirmSendEmails');
        sendBtn.disabled = true;
        sendBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span> Loading preview...`;

        bsModal.show();

        try {
            const resp = await fetch(`/api/jobs/${jobId}/email-preview`);
            const data = await resp.json();

            if (!data.success) {
                document.getElementById('preFlightSmtpTitle').textContent = 'Preview Error';
                document.getElementById('preFlightSmtpMessage').textContent = data.message || 'Unable to retrieve preview.';
                document.getElementById('preFlightSmtpAlert').classList.remove('d-none');
                sendBtn.innerHTML = `<i class="bi bi-x-circle me-1"></i> Preview Failed`;
                return;
            }

            // Populate Job Info
            document.getElementById('preFlightJobTitle').textContent = data.title || 'Webinar Session';
            document.getElementById('preFlightInputType').textContent = (data.input_type === 'video' ? 'Video (MP4)' : 'Transcript');

            // Populate Counts
            document.getElementById('preFlightTotalCount').textContent = data.counts.total;
            document.getElementById('preFlightEligibleCount').textContent = data.counts.eligible_to_send;
            document.getElementById('preFlightSentCount').textContent = data.counts.sent;
            document.getElementById('preFlightFailedCount').textContent = data.counts.failed;

            // Render preview table
            const tbody = document.getElementById('preFlightRecipientsTableBody');
            tbody.innerHTML = '';
            if (data.preview_recipients && data.preview_recipients.length > 0) {
                data.preview_recipients.forEach(r => {
                    const tr = document.createElement('tr');
                    let badgeClass = 'bg-secondary-subtle text-secondary';
                    if (r.status === 'sent') badgeClass = 'bg-success-subtle text-success';
                    else if (r.status === 'failed') badgeClass = 'bg-danger-subtle text-danger';

                    tr.innerHTML = `
                        <td class="font-monospace">${safeEscapeHtml(r.email)}</td>
                        <td>${safeEscapeHtml(r.name || '--')}</td>
                        <td><span class="badge ${badgeClass}">${safeEscapeHtml(r.status)}</span></td>
                    `;
                    tbody.appendChild(tr);
                });
                document.getElementById('preFlightPreviewNote').textContent = `Showing ${data.preview_recipients.length} of ${data.counts.total}`;
            } else {
                tbody.innerHTML = `<tr><td colspan="3" class="text-center text-muted py-2">No recipients registered.</td></tr>`;
            }

            // SMTP verification
            if (!data.smtp_ready) {
                document.getElementById('preFlightSmtpTitle').textContent = 'SMTP Configuration Required';
                document.getElementById('preFlightSmtpMessage').textContent = data.smtp_error || 'Please configure valid SMTP settings in your environment (.env).';
                document.getElementById('preFlightSmtpAlert').classList.remove('d-none');
                sendBtn.disabled = true;
                sendBtn.innerHTML = `<i class="bi bi-lock-fill me-1"></i> SMTP Incomplete`;
                return;
            }

            // Check if there are eligible recipients
            if (data.counts.eligible_to_send <= 0) {
                const feedbackAlert = document.getElementById('preFlightFeedbackAlert');
                feedbackAlert.className = 'alert alert-info border-0 small rounded-3 mb-0';
                feedbackAlert.innerHTML = '<i class="bi bi-info-circle me-1"></i> All recipients have already received the summary PDF.';
                feedbackAlert.classList.remove('d-none');
                sendBtn.disabled = true;
                sendBtn.innerHTML = `<i class="bi bi-check2-all me-1"></i> All Delivered`;
                return;
            }

            // Ready to send
            sendBtn.disabled = false;
            sendBtn.innerHTML = `<i class="bi bi-send-fill me-1"></i> ${isRetry ? 'Retry Delivery' : 'Confirm & Send Emails'}`;

        } catch (err) {
            document.getElementById('preFlightSmtpTitle').textContent = 'Connection Error';
            document.getElementById('preFlightSmtpMessage').textContent = err.message;
            document.getElementById('preFlightSmtpAlert').classList.remove('d-none');
            sendBtn.innerHTML = `<i class="bi bi-x-circle me-1"></i> Error`;
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        const sendBtn = document.getElementById('btnConfirmSendEmails');
        if (sendBtn) {
            sendBtn.addEventListener('click', async () => {
                if (!currentActiveJobId) return;

                const endpoint = currentIsRetryMode ? `/api/jobs/${currentActiveJobId}/retry-emails` : `/api/jobs/${currentActiveJobId}/send-emails`;
                sendBtn.disabled = true;
                sendBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span> Sending emails...`;

                const feedbackAlert = document.getElementById('preFlightFeedbackAlert');
                feedbackAlert.className = 'alert alert-info border-0 small rounded-3 mb-0';
                feedbackAlert.innerHTML = `
                    <div class="d-flex align-items-center gap-2">
                        <span class="spinner-border spinner-border-sm text-primary" role="status"></span>
                        <div>Connecting to SMTP server and transmitting summary PDFs to students...</div>
                    </div>
                `;
                feedbackAlert.classList.remove('d-none');

                try {
                    const resp = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    });
                    const result = await resp.json();

                    if (result.success) {
                        feedbackAlert.className = 'alert alert-success border-0 small rounded-3 mb-0';
                        feedbackAlert.innerHTML = `
                            <div class="d-flex align-items-center gap-2">
                                <i class="bi bi-check-circle-fill text-success fs-5"></i>
                                <div><strong>Delivery Completed!</strong> ${result.message}</div>
                            </div>
                        `;
                        setTimeout(() => {
                            window.location.reload();
                        }, 1200);
                    } else {
                        feedbackAlert.className = 'alert alert-danger border-0 small rounded-3 mb-0';
                        feedbackAlert.innerHTML = `
                            <div class="d-flex align-items-start gap-2">
                                <i class="bi bi-exclamation-triangle-fill text-danger fs-5 mt-1"></i>
                                <div><strong>Sending Failed:</strong> ${result.message}</div>
                            </div>
                        `;
                        sendBtn.disabled = false;
                        sendBtn.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Retry`;
                    }
                } catch (err) {
                    feedbackAlert.className = 'alert alert-danger border-0 small rounded-3 mb-0';
                    feedbackAlert.innerHTML = `<strong>Network Error:</strong> ${err.message}`;
                    sendBtn.disabled = false;
                    sendBtn.innerHTML = `<i class="bi bi-arrow-repeat me-1"></i> Retry`;
                }
            });
        }
    });

    window.openDeliveryReportModal = async function(jobId) {
        currentActiveJobId = jobId;
        const modalEl = document.getElementById('deliveryReportModal');
        if (!modalEl) return;
        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);

        document.getElementById('reportJobId').textContent = '#' + jobId;
        const retryBtn = document.getElementById('btnReportRetryFailed');
        retryBtn.classList.add('d-none');

        bsModal.show();

        try {
            const resp = await fetch(`/api/jobs/${jobId}/delivery-report`);
            const data = await resp.json();

            if (!data.success) {
                alert(data.message || 'Unable to retrieve delivery report.');
                return;
            }

            document.getElementById('reportJobTitle').textContent = data.title || 'Webinar Session';
            document.getElementById('reportCompletedAt').textContent = data.completed_at || 'In Progress';

            // Badge
            const overallBadge = document.getElementById('reportOverallBadge');
            if (data.email_status === 'completed') {
                overallBadge.className = 'badge bg-success-subtle text-success border border-success-subtle px-3 py-1.5 rounded-pill';
                overallBadge.textContent = 'Completed (All Sent)';
            } else if (data.email_status === 'partially_sent') {
                overallBadge.className = 'badge bg-warning-subtle text-warning-emphasis border border-warning-subtle px-3 py-1.5 rounded-pill';
                overallBadge.textContent = 'Partially Delivered';
            } else if (data.email_status === 'sending') {
                overallBadge.className = 'badge bg-primary-subtle text-primary border border-primary-subtle px-3 py-1.5 rounded-pill';
                overallBadge.textContent = 'Sending...';
            } else {
                overallBadge.className = 'badge bg-danger-subtle text-danger border border-danger-subtle px-3 py-1.5 rounded-pill';
                overallBadge.textContent = data.email_status ? data.email_status.toUpperCase() : 'FAILED';
            }

            // Stats
            document.getElementById('reportStatTotal').textContent = data.counts.total;
            document.getElementById('reportStatAccepted').textContent = data.counts.sent;
            document.getElementById('reportStatFailed').textContent = data.counts.failed;
            document.getElementById('reportStatPending').textContent = data.counts.pending;

            // Render table
            const tbody = document.getElementById('reportRecipientsTableBody');
            tbody.innerHTML = '';

            if (data.recipients && data.recipients.length > 0) {
                data.recipients.forEach(r => {
                    const tr = document.createElement('tr');
                    let statusBadge = '<span class="badge bg-secondary-subtle text-secondary">Pending</span>';
                    if (r.status === 'sent') {
                        statusBadge = '<span class="badge bg-success-subtle text-success"><i class="bi bi-check-circle me-1"></i>Accepted</span>';
                    } else if (r.status === 'failed') {
                        statusBadge = '<span class="badge bg-danger-subtle text-danger"><i class="bi bi-x-circle me-1"></i>Failed</span>';
                    }

                    tr.innerHTML = `
                        <td class="font-monospace fw-semibold">${safeEscapeHtml(r.email)}</td>
                        <td>${safeEscapeHtml(r.name || '--')}</td>
                        <td>${statusBadge}</td>
                        <td>${r.attempts || 0}</td>
                        <td class="text-muted small">${r.sent_at || '--'}</td>
                        <td class="small text-truncate" style="max-width: 180px;" title="${safeEscapeHtml(r.last_error || (r.status === 'sent' ? 'SMTP 250 Accepted' : 'None'))}">
                            ${safeEscapeHtml(r.last_error || (r.status === 'sent' ? 'SMTP 250 Accepted' : '--'))}
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-3">No recipient delivery records found.</td></tr>`;
            }

            // Retry button toggle
            if (data.can_retry) {
                retryBtn.classList.remove('d-none');
            } else {
                retryBtn.classList.add('d-none');
            }

        } catch (err) {
            alert('Failed to load delivery report: ' + err.message);
        }
    };

    window.triggerRetryFromReport = function() {
        const reportModalEl = document.getElementById('deliveryReportModal');
        if (reportModalEl) {
            const bsReport = bootstrap.Modal.getInstance(reportModalEl);
            if (bsReport) bsReport.hide();
        }
        if (currentActiveJobId) {
            window.openEmailPreFlightModal(currentActiveJobId, true);
        }
    };
})();

