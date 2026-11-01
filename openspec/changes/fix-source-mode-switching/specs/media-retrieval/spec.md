# Spec Delta

## Purpose

Enforces intuitive and responsive multi-source webinar content selection, ensuring strict mutual exclusivity between manual upload controls and automated retrieval options like YouTube.

## ADDED Requirements

### Requirement: Source Mode Mutual Exclusivity and Panel Visibility
The dashboard SHALL display the selected content source panel and immediately hide all unselected panels, including the manual format mode controls, upon user selection.

#### Scenario: Selecting YouTube hides manual format mode and displays YouTube panel
- **WHEN** the user selects the YouTube content source mode
- **THEN** the system hides the manual format mode section and displays the YouTube URL input panel

#### Scenario: Selecting other automated sources hides manual format mode
- **WHEN** the user selects Direct Link, Google Drive, Local File, or Local Folder
- **THEN** the system hides the manual format mode section and displays the selected source panel

#### Scenario: Switching back to Manual Upload restores manual format mode
- **WHEN** the user selects the Manual Upload option after viewing another source
- **THEN** the system hides the other source panels and restores the manual format mode controls

### Requirement: Source Input Autofocus and Clean Script Initialization
The system SHALL ensure client dashboard scripts initialize without syntax errors and automatically focus the target input field when an automated URL-based source is selected.

#### Scenario: Client-side script initializes without error
- **WHEN** the dashboard page loads in the client browser
- **THEN** all dashboard scripts execute cleanly without uncaught syntax errors or duplicate declaration exceptions

#### Scenario: YouTube input is focused on selection
- **WHEN** the user clicks the YouTube source option
- **THEN** the system sets input focus to the YouTube URL input field for immediate link entry

