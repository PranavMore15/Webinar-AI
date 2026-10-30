# WebinarAI — Complete Project Specification and Staged Implementation Plan

## CRITICAL INSTRUCTIONS FOR ANTIGRAVITY

This document contains the complete specification for my college mega project:

**WebinarAI: AI-Powered Webinar Summarization and Knowledge Distribution Platform**

Read the entire specification and save it as `PROJECT_SPEC.md` in the project root.

Also create `PROJECT_STATUS.md` to track the project's current state, completed stages, pending work, known issues, configuration requirements, and next steps.

### Current workspace state

- Project folder: `WebinarAI`
- The project folder is currently empty.
- No application source code or Python project dependencies have been created.
- MySQL Workbench is already installed.
- An existing MySQL connection named `Local WebinarAI DB` is available.
- MySQL Community Server is connected at `localhost:3306`.
- The current MySQL connection uses the `root` account.
- MySQL authentication plugin shown: `caching_sha2_password`.
- The password I currently use for this local MySQL setup is `student`.
- Do not assume the actual database/schema is named `Local WebinarAI DB`; that is the saved connection's display name.
- Python, FFmpeg, and other development dependencies have not yet been verified.

### Execution rule — Read carefully

**For now, execute Prompt 0 only.**

Prompt 0 is the workspace inspection and planning stage described in Part K.

You must not execute Prompt 1 or any subsequent implementation stage until I explicitly approve it.

During Prompt 0:

- Inspect the workspace and available development tools.
- Save this specification as `PROJECT_SPEC.md`.
- Create `PROJECT_STATUS.md`.
- Prepare the implementation roadmap.
- Prioritize a demonstrable prototype for tomorrow's college progress presentation.
- Do not build the application yet.
- Do not install software or Python packages.
- Do not create database tables or schemas.
- Do not change system settings or MySQL configuration.
- Do not modify or delete existing databases.
- Do not expose passwords or secrets.
- Stop after reporting your findings and wait for my approval.

Do not ask me to submit this specification again. Use the saved `PROJECT_SPEC.md` as the source of truth for future stages.

---

# PART A — PROJECT OVERVIEW

## 1. Project title

**WebinarAI: AI-Powered Webinar Summarization and Knowledge Distribution Platform**

## 2. Problem statement

Students frequently miss webinars, guest lectures, technical sessions, and educational workshops because of timetable conflicts, personal commitments, or limited availability.

Even when recordings are available, watching an entire webinar can take considerable time. Students may also struggle to identify important discussions, technical concepts, and key takeaways.

WebinarAI aims to solve this problem by processing an existing webinar recording or transcript, generating an AI-powered summary, extracting key points and main topics, producing a downloadable PDF, and distributing that PDF to the intended student recipients through email.

## 3. Main objective

Build a functional web application that allows an authorized user to upload existing webinar content and a CSV file containing student email addresses.

The system processes the webinar content, generates a summary PDF, validates the recipient list, and emails the generated PDF to valid recipients.

This is a post-webinar processing and knowledge-distribution platform. It is not a webinar hosting or video-conferencing platform.

## 4. Initial project scope

The initial application must support:

1. Authorized user login.
2. Uploading an MP4 webinar recording or a transcript file.
3. Uploading a student email CSV independently of the webinar content upload.
4. CSV validation, duplicate detection, and invalid-row reporting.
5. Video transcription using FFmpeg and Whisper.
6. Transcript processing without unnecessary video-transcription steps.
7. AI summarization using the Google Gemini API.
8. PDF generation using ReportLab.
9. Email delivery through SMTP.
10. Processing-job tracking and error reporting.
11. A dashboard showing processing and email-delivery results.

Do not implement webinar hosting, live meeting integrations, Zoom/Meet/Teams scheduling, automatic participant retrieval, or a student chatbot in the initial version.

Those features may be considered future enhancements.

---

# PART B — TECHNOLOGY STACK

## 5. Frontend

Use:

- HTML5
- CSS3
- JavaScript
- Bootstrap 5

The interface must be responsive, clean, professional, and suitable for a college engineering mega-project demonstration.

Do not introduce React, Angular, or another frontend framework unless I approve the change.

## 6. Backend

Use:

- Python
- Flask
- Flask-Login or an appropriate equivalent authentication solution
- MySQL Connector/Python or SQLAlchemy
- `python-dotenv` for environment configuration

Keep the code modular and beginner-friendly.

## 7. Database

Use MySQL to store application metadata, including:

- User accounts
- Processing-job records
- Input file metadata
- Recipient email records
- Processing status
- Email-delivery status
- Error information
- Timestamps

Do not store large video files directly in MySQL.

## 8. AI and media processing

Use:

- FFmpeg for extracting audio from MP4 recordings.
- Whisper for speech-to-text transcription.
- Google Gemini API for summarization and key-point extraction.
- ReportLab for PDF creation.
- SMTP for email delivery.

Use the official Google GenAI Python SDK and supported API patterns.

Store credentials in environment variables. Never hardcode API keys.

## 9. Dependency management

Use a Python virtual environment named `.venv`.

Maintain a `requirements.txt` file containing the application's actual Python dependencies.

Keep the dependency list as small as reasonably possible.

Check Python and library compatibility before installing dependencies.

Do not introduce Docker, Redis, Celery, cloud hosting, or a vector database into the initial version unless a demonstrated requirement justifies it and I approve the change.

---

# PART C — EXISTING MYSQL CONFIGURATION

## 10. MySQL environment

MySQL Workbench is already installed and shows an active connection with these details:

- Saved connection name: `Local WebinarAI DB`
- Server: MySQL Community Server
- Host: `localhost`
- Port: `3306`
- Username: `root`
- Authentication plugin: `caching_sha2_password`
- Connection status: Connected

The local MySQL password currently used by me is `student`.

This password is provided only to explain the existing development environment. Treat it as sensitive.

### During Prompt 0

1. Do not reinstall MySQL Server or MySQL Workbench.
2. Do not assume that the connection name is the schema name.
3. Do not attempt to change the password.
4. Do not connect automatically, execute database commands, create schemas, or modify databases without my approval.
5. Report that MySQL is already available according to my supplied connection status.
6. Check only what can safely be verified from the workspace and available tools.
7. Do not claim that a schema exists unless it has actually been verified.

### During the later database implementation stage

After I approve the database stage:

1. Reuse the existing MySQL Server.
2. Use `localhost:3306` unless verification identifies a different configuration.
3. Confirm that the `root` account can be used by the application, without exposing credentials.
4. Ask me to confirm the appropriate credentials before configuring the application connection.
5. Prefer creating a dedicated application database named `webinar_ai_db`.
6. Do not assume that `Local WebinarAI DB` is the actual database/schema.
7. Do not drop, overwrite, or modify unrelated databases.
8. Never print the password in terminal instructions, generated reports, source code, or application logs.
9. Use environment variables for database configuration.
10. If possible, recommend a dedicated application database user with limited privileges rather than using the root account permanently.
11. Use parameterized SQL queries or a suitable ORM.

Example `.env` configuration for the eventual application:

`DB_HOST=localhost`

`DB_PORT=3306`

`DB_NAME=webinar_ai_db`

`DB_USER=your_confirmed_username`

`DB_PASSWORD=your_local_database_password`

The example is illustrative. Use the actual configuration only after I approve the database setup.

The `.env` file must be excluded from version control. The `.env.example` file must contain placeholders only.

---

# PART D — APPLICATION WORKFLOW

## 11. Authentication

Create a login system for authorized users.

Requirements:

- Secure password hashing.
- Protected dashboard and processing routes.
- Appropriate session management.
- Input validation.
- Logout functionality.
- No plaintext password storage.

For the initial demonstration, provide documented instructions for creating the first authorized account safely.

Do not introduce public registration unless it is justified and approved.

## 12. Dashboard design

Create one primary dashboard with two independent upload sections.

### Section A — Upload webinar content

Provide two mutually exclusive input choices.

**Option 1: Upload webinar video**

- Accept MP4 files.
- Display the selected filename.
- Show file size and validation errors where practical.
- Allow the user to replace the selected file.

**Option 2: Upload transcript**

- Accept TXT and VTT files.
- Display the selected filename.
- Validate the file extension and type.
- Allow the user to replace the selected file.

Only one webinar input should be selected for a particular processing job.

### Section B — Upload student email CSV

Provide a separate CSV upload control.

The user must be able to upload webinar content and the email CSV in either order.

Uploading the CSV should trigger validation and display a preview without requiring webinar content first.

Uploading webinar content must not require the CSV to be present immediately.

### Main action button

Provide one primary button:

**Start Processing & Deliver Email**

Keep this button disabled until:

- A valid webinar video or transcript is selected.
- A valid CSV has been uploaded.
- At least one valid, unique email address exists.

Revalidate the current server-side state when the button is clicked.

Prevent accidental duplicate submissions.

---

# PART E — STUDENT EMAIL CSV VALIDATION

## 13. CSV format

Support CSV files containing at least an email column.

Example:

`email,name`

`student1@example.com,Student One`

`student2@example.com,Student Two`

The name column is optional.

Recognize email-column names case-insensitively, including `email`, `Email`, and `EMAIL`.

Do not require student names.

## 14. CSV validation rules

Implement:

1. Safe CSV parsing.
2. Trimming leading and trailing whitespace.
3. Basic email-address syntax validation.
4. Case-insensitive duplicate detection.
5. Preservation of the first valid occurrence.
6. Separate counts for blank and malformed email addresses.
7. Duplicate-row and invalid-row reporting.
8. Clear reasons for rejected rows.
9. A preview of valid, unique recipients.
10. Inspection of invalid and duplicate rows.
11. No silent dropping of validation problems.
12. No email sending to invalid or duplicate addresses.
13. Prevention of processing when no valid unique recipients remain.

Display:

- Total data rows.
- Valid unique email addresses.
- Duplicate addresses removed.
- Invalid email addresses.
- Blank email fields.

Repeat validation on the backend. Do not rely only on frontend checks.

Do not send emails automatically when a CSV is uploaded.

---

# PART F — VIDEO AND TRANSCRIPT PROCESSING

## 15. Video input pipeline

For MP4 input:

1. Validate the file and enforce reasonable size limits.
2. Save the file using a generated, safe filename.
3. Extract audio using FFmpeg.
4. Convert audio to a Whisper-supported format.
5. Transcribe the audio using Whisper.
6. Split long audio into manageable chunks when necessary.
7. Combine transcript chunks in the correct order.
8. Clean and normalize the transcript.
9. Verify that the resulting transcript is usable and non-empty.
10. Pass the transcript to the common AI pipeline.

Handle missing audio, unsupported media, transcription failures, timeouts, and insufficient resources gracefully.

Do not mark failed transcription as successful.

Do not proceed to email delivery if transcription fails.

## 16. Transcript input pipeline

For TXT input:

- Read text safely.
- Handle supported text encodings.
- Remove irrelevant whitespace.
- Validate that meaningful transcript content exists.

For VTT input:

- Remove the WebVTT header.
- Remove cue timestamps and cue identifiers.
- Remove formatting artifacts where appropriate.
- Preserve meaningful spoken content and speaker labels.
- Avoid accidentally deleting transcript sentences.

Transcript uploads must not invoke FFmpeg or Whisper.

Both input paths must produce a usable transcript for the common AI pipeline.

---

# PART G — AI SUMMARIZATION

## 17. Gemini integration

Use the Google Gemini API through the official supported Python SDK.

Store the API key in an environment variable.

Generate:

1. Webinar title, if available.
2. A concise but informative summary.
3. Important key points.
4. Main topics discussed.
5. Important technical concepts and takeaways supported by the transcript.

The output should be suitable for engineering students and educational use.

## 18. Summarization quality

Summarize only information supported by the supplied transcript.

Do not invent speakers, facts, discussions, conclusions, or technical claims.

For long transcripts:

- Split content into manageable chunks.
- Summarize chunks when necessary.
- Combine intermediate summaries into a coherent final summary.
- Preserve important concepts and relationships.
- Respect the selected model's context and output limits.

Handle API failures, rate limits, timeouts, malformed output, and temporary errors with bounded retries and understandable error messages.

If summarization fails, record the failure and do not send an incomplete or fabricated summary PDF.

---

# PART H — PDF GENERATION

## 19. PDF requirements

Use ReportLab to generate a professional, readable PDF.

Include, where available:

- Webinar title.
- Generation date.
- Webinar summary.
- Key points.
- Main topics.
- Important technical takeaways.

The PDF should have clear headings, consistent spacing, readable typography, appropriate page breaks, and relevant Unicode support.

Verify that the PDF has been successfully created and can be read before marking it ready for delivery.

Make the PDF available to the authorized user through the dashboard.

Never email a PDF before it has been generated and verified.

---

# PART I — EMAIL DELIVERY

## 20. SMTP integration

Use SMTP for the initial version.

Store these settings in environment variables:

- SMTP host.
- SMTP port.
- SMTP username.
- SMTP password or application-specific credential.
- Sender email address.
- TLS configuration.

Create a professional subject and email body, including the webinar title when available.

Attach the generated PDF.

Never expose credentials in the frontend, logs, source control, or API responses.

## 21. Recipient handling

- Send only to valid, unique recipient addresses.
- Do not reveal other students' addresses to recipients.
- Prefer individual messages for the initial version.
- Track the status of each recipient.
- Continue sending if one address fails.
- Record failures and useful diagnostic information.
- Allow retries of failed recipients without rerunning AI summarization.
- Prevent duplicate delivery caused by refreshes or repeated submissions.

Distinguish between SMTP acceptance and confirmed inbox delivery.

Email delivery is a core initial feature, not a future enhancement.

---

# PART J — PROCESSING JOBS AND STATUS TRACKING

## 22. Processing jobs

Each submitted webinar workflow must have a unique processing-job ID.

A job represents one attempt to process a webinar and distribute its PDF.

Store relevant information such as:

- Job ID.
- Authenticated user ID.
- Input type.
- Input file metadata.
- Transcript status.
- Summary status.
- PDF status.
- Total recipient count.
- Successful email count.
- Failed email count.
- Creation and completion timestamps.
- Error information.

## 23. Job statuses

Use meaningful states that represent actual progress:

- Ready to Start.
- Queued.
- Extracting Audio, for video input only.
- Transcribing, for video input only.
- Cleaning Transcript.
- Generating Summary.
- Generating PDF.
- Ready to Send.
- Sending Emails.
- Completed.
- Completed with Some Email Failures.
- Failed.

Do not display fabricated progress percentages.

The dashboard must show the current state, input type, PDF availability, recipient counts, and actionable errors.

Refreshing the dashboard or reopening a job must not restart processing.

## 24. Background processing

Do not perform lengthy video transcription and summarization entirely inside a long-running Flask request.

During implementation planning, choose an appropriate background-processing design for lengthy tasks.

Keep the infrastructure lightweight. Do not add Redis or Celery without a clear requirement and my approval.

Keep the application responsive during processing.

---

# PART K — DATABASE AND SECURITY

## 25. Suggested database structure

### Users

- id
- email or username
- password_hash
- created_at

### ProcessingJobs

- id
- user_id
- input_type
- input_file_path or controlled storage reference
- transcript status
- summary status
- PDF path
- overall status
- recipient totals
- error information
- created_at
- updated_at
- completed_at

### JobRecipients

- id
- job_id
- email
- optional student name
- delivery status
- attempt_count
- last_error
- sent_at

Use primary keys, foreign keys, appropriate indexes, and unique constraints.

Adapt the schema only when justified and document any changes.

Store paths and metadata in MySQL, not the binary contents of large recordings.

## 26. Security requirements

Implement:

- Password hashing.
- Authentication and authorization checks.
- CSRF protection for state-changing browser requests.
- Parameterized SQL queries or a safe ORM.
- Secure session configuration.
- File-extension and file-size validation.
- Generated filenames.
- Protection against path traversal.
- Controlled file storage.
- Environment variables for secrets.
- `.gitignore` excluding `.env`, `.venv`, generated files, and sensitive data.
- `.env.example` with placeholders only.
- Safe error messages.
- Reasonable upload and request limits.
- Job ownership checks before accessing results or downloading PDFs.

Do not log passwords, API keys, SMTP credentials, or unnecessary student information.

## 27. File retention

Use a documented retention and cleanup policy.

Delete temporary audio when it is no longer needed, while preserving files required for supported retries.

Do not delete source files prematurely if they are needed for failed-job recovery.

Keep generated PDFs available under the defined retention policy.

---

# PART L — STAGED IMPLEMENTATION PROMPTS

Execute each stage separately. Each stage requires my explicit approval before execution.

## Prompt 0 — Workspace inspection and planning

Inspect the empty `WebinarAI` workspace and available development environment.

Check whether Python, pip, FFmpeg, Git, VS Code or the Antigravity editor, and MySQL command-line tools are available.

Use the MySQL connection details provided in Part C as context. Do not attempt database modifications.

Produce:

1. An environment-readiness report.
2. A list of missing tools and prerequisites.
3. A proposed project folder structure.
4. A staged implementation roadmap.
5. A risk assessment covering Whisper, video-processing resources, Gemini API access, SMTP, and long-running jobs.
6. A next-day demonstration plan.
7. A list of features that can be completed without external API credentials.
8. A list of configuration items requiring my input.

Save this specification as `PROJECT_SPEC.md`.

Create `PROJECT_STATUS.md` with the initial state, roadmap, and next task.

You may create or update these planning documents. Do not create application implementation files, install software or packages, change system configuration, create database tables, or modify existing databases.

After finishing, explain your findings and recommended next steps.

**Stop and wait for my approval.**

## Prompt 1 — Demo-ready foundation and frontend

After approval, establish the initial runnable project.

Prioritize the next-day college demonstration.

Create the minimum necessary Flask application and a professional responsive dashboard.

Implement:

- Application entry point.
- Basic Flask routes.
- Shared layout and styling.
- Login interface and an appropriate authentication foundation.
- Webinar video/transcript selection interface.
- Separate student email CSV upload interface.
- Upload filename and validation displays.
- Processing-status panel.
- Empty states and error states.
- Main action button with appropriate initial disabled state.
- A working local run command.
- README with setup and launch instructions.

Do not claim AI summarization, PDF creation, or email delivery works until implemented and tested.

Use synthetic demonstration data only when needed and label simulated states clearly.

## Prompt 2 — Authentication and database

After approval, implement MySQL connectivity, the required tables, secure login, sessions, ownership checks, and processing-job persistence.

Reuse the existing MySQL Server and connection.

Use `webinar_ai_db` as the proposed application schema after verifying availability and receiving approval.

Create a documented database initialization procedure.

Verify that a user can log in and a processing-job record can be created and retrieved.

## Prompt 3 — File uploads and CSV validation

After approval, implement safe uploads for MP4, TXT, and VTT.

Implement CSV parsing, email validation, duplicate handling, invalid-row reporting, and preview functionality.

Allow the two upload sections to be used independently and in either order.

Enable the main processing button only when both input requirements are satisfied.

Test empty CSVs, malformed files, duplicate addresses with different capitalization, blank addresses, invalid addresses, and valid lists.

## Prompt 4 — Transcript and video processing

After approval, implement TXT and VTT parsing first, then integrate FFmpeg and Whisper for MP4 input.

Verify both input paths produce valid transcripts and report failures accurately.

Do not invoke transcription tools for TXT or VTT uploads.

## Prompt 5 — Gemini summarization

After approval, integrate Gemini, implement structured summarization, long-transcript handling, error management, and summary validation.

Verify the output contains the expected summary, key points, and main topics.

## Prompt 6 — PDF generation

After approval, generate the PDF using ReportLab and verify its content, readability, and storage path.

Provide an authorized dashboard download.

## Prompt 7 — SMTP email delivery

After approval, configure SMTP, send the PDF to validated recipients, track attempts and errors, and support retrying failed recipients without regenerating the summary.

Use a controlled test recipient for initial testing.

Do not send test messages to real student lists without my approval.

## Prompt 8 — Integration and job orchestration

After approval, connect all completed modules into one end-to-end workflow.

Enforce these rules:

- Uploads may occur in either order.
- One job uses exactly one webinar input.
- A job cannot start without a valid unique recipient list.
- Processing starts only after server-side validation.
- Email sending begins only after successful PDF generation and verification.
- Transcription or summarization failure must never trigger email delivery.
- A failed recipient must not prevent delivery attempts to other valid recipients.
- Refreshing a page must not create duplicate jobs or messages.
- Job statuses must represent actual system state.

Implement and test an appropriate background-processing approach for lengthy tasks.

## Prompt 9 — Testing, security, documentation, and final review

After approval, test the complete application and fix integration problems.

Cover:

1. MP4 plus valid CSV.
2. TXT plus valid CSV.
3. VTT plus valid CSV.
4. Uploads in either order.
5. Invalid CSV entries and duplicate removal.
6. Empty recipient list.
7. Video transcription failure.
8. Gemini API failure.
9. PDF generation failure.
10. Individual SMTP delivery failure.
11. Refresh and resubmission behavior.
12. Authentication and job ownership.
13. Safe file handling and secret management.
14. Dashboard status accuracy.

Update README with installation, configuration, database setup, running, testing, and troubleshooting instructions.

Update `PROJECT_STATUS.md` with actual implementation results and remaining limitations.

Never report a test as passing unless it was actually executed and verified.

---

# PART M — NEXT-DAY COLLEGE DEMONSTRATION

## 28. Demonstration priority

My immediate priority is to show meaningful, credible project progress to my college teachers tomorrow.

After Prompt 0 is approved, prioritize a small but genuinely functional demonstration.

Preferred order:

1. Running Flask application.
2. Professional dashboard.
3. Working webinar input selection and upload interface.
4. Working CSV email validation and duplicate detection.
5. A processing-job record and visible status.
6. A basic end-to-end demonstration with a small, non-sensitive test file.
7. Real AI summarization, PDF generation, and email delivery as soon as their prerequisites are ready.

If time is limited, complete and test the earlier features before attempting every advanced feature.

Use clearly labeled placeholders for unfinished features. Do not fake successful processing or email delivery.

Prepare a concise demonstration script explaining the problem, solution, technology stack, implemented modules, and remaining work.

## 29. Development rules

Throughout the project:

- Work only on the stage I have approved.
- Read `PROJECT_SPEC.md` before starting a new stage.
- Update `PROJECT_STATUS.md` after completing each stage.
- Inspect existing files before changing them.
- Do not overwrite working code without a clear reason.
- Keep modules small and understandable.
- Prefer readable, beginner-friendly Python.
- Avoid unnecessary abstractions and dependencies.
- Explain new files and important changes.
- Give exact terminal commands for setup and testing.
- Run relevant tests before declaring a stage complete.
- Request my approval before moving to the next stage.
- Report blockers instead of silently inventing solutions.

## 30. Definition of success

WebinarAI is successful when an authorized user can upload an existing webinar video or transcript, upload and validate a separate student email CSV, initiate a processing job, generate a meaningful AI summary and PDF, and email that PDF to valid unique recipients while tracking progress and failures.

The implementation must be secure, testable, understandable, and suitable for an engineering mega-project demonstration.

---

# FINAL INSTRUCTION — EXECUTE PROMPT 0 ONLY

Save the complete specification as `PROJECT_SPEC.md`.

Create `PROJECT_STATUS.md`.

Inspect the workspace and available tools.

Account for the existing MySQL Server and Workbench setup described in Part C. Do not reinstall MySQL or modify any database during Prompt 0.

Prepare the implementation plan and next-day demonstration roadmap.

**Do not execute Prompt 1 or any subsequent prompt. Do not build the application yet. Do not install dependencies. Do not modify database schemas.**

Present the findings and next steps, then stop and wait for my explicit approval.
