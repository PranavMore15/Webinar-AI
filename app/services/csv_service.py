import io
import re
import csv

# Standard RFC 5322-compliant simplified email syntax validation pattern
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

class CSVValidationError(Exception):
    """Custom exception for CSV validation failures."""
    pass

def validate_and_parse_csv(file_bytes: bytes, filename: str, max_size_bytes: int = 10 * 1024 * 1024, existing_recipients: list = None):
    """
    Safely validates, parses, and audits student recipient CSV content.
    
    Rules enforced:
    1. Extension and size limits.
    2. Encoding detection and safe decoding (UTF-8, UTF-8 with BOM, Latin-1 fallback).
    3. Empty file detection.
    4. Required 'email' column check (case-insensitive, e.g. email, Email, EMAIL).
    5. Optional 'name' column.
    6. Trimming leading/trailing whitespace.
    7. Separation of blank email rows vs malformed email syntax rows.
    8. Case-insensitive duplicate detection preserving the first valid occurrence.
    9. Actionable row numbering (1-indexed based on data rows).
    """
    if not filename or not filename.lower().endswith('.csv'):
        return {
            'success': False,
            'error': 'Unsupported file type. Only .csv files are accepted.',
            'code': 'INVALID_EXTENSION'
        }
    
    if len(file_bytes) > max_size_bytes:
        return {
            'success': False,
            'error': f'File size exceeds the allowable limit of {max_size_bytes // (1024 * 1024)}MB.',
            'code': 'FILE_TOO_LARGE'
        }

    if not file_bytes or len(file_bytes.strip()) == 0:
        return {
            'success': False,
            'error': 'The uploaded CSV file is empty.',
            'code': 'EMPTY_FILE'
        }

    # Decode content safely
    content = None
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            content = file_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        return {
            'success': False,
            'error': 'Unable to decode CSV file. Please ensure it is saved in UTF-8 or standard ASCII format.',
            'code': 'DECODE_ERROR'
        }

    # Parse CSV stream
    try:
        # Use StringIO to read line by line with standard csv.reader
        stream = io.StringIO(content, newline='')
        reader = csv.reader(stream)
        
        # Read header row
        try:
            header_row = next(reader)
        except StopIteration:
            return {
                'success': False,
                'error': 'The uploaded CSV file contains no header or data rows.',
                'code': 'EMPTY_FILE'
            }

        if not header_row:
            return {
                'success': False,
                'error': 'CSV header row is empty.',
                'code': 'MISSING_HEADER'
            }

        # Normalize header columns
        cleaned_headers = [str(col).strip().lower() for col in header_row]
        
        email_col_idx = -1
        name_col_idx = -1

        for idx, col_name in enumerate(cleaned_headers):
            if col_name == 'email':
                email_col_idx = idx
            elif col_name in ('name', 'student_name', 'full_name', 'student name'):
                name_col_idx = idx

        if email_col_idx == -1:
            return {
                'success': False,
                'error': 'Missing required "email" column in CSV header. Recognized header names: email, Email, EMAIL.',
                'code': 'MISSING_EMAIL_COLUMN'
            }

        # Process data rows
        total_data_rows = 0
        valid_recipients = []
        seen_emails = set()
        if existing_recipients:
            for item in existing_recipients:
                if isinstance(item, dict) and 'email' in item:
                    seen_emails.add(str(item['email']).lower().strip())
                elif isinstance(item, str):
                    seen_emails.add(item.lower().strip())
        duplicate_rows = []
        invalid_rows = []
        blank_rows = []

        row_number = 1  # 1-indexed relative to data rows (header is row 0)

        for row in reader:
            # Skip completely empty lines
            if not row or all(len(cell.strip()) == 0 for cell in row):
                continue

            total_data_rows += 1
            
            # Extract raw email
            raw_email = row[email_col_idx].strip() if email_col_idx < len(row) else ''
            
            # Extract optional name
            student_name = ''
            if name_col_idx != -1 and name_col_idx < len(row):
                student_name = row[name_col_idx].strip()

            # Rule 1: Check for blank email field
            if not raw_email:
                blank_entry = {
                    'row': row_number + 1,  # actual file line number (header is line 1)
                    'email': '[BLANK]',
                    'name': student_name or '[None]',
                    'reason': 'Blank or empty email address field'
                }
                blank_rows.append(blank_entry)
                invalid_rows.append(blank_entry)
                row_number += 1
                continue

            # Rule 2: Validate email syntax
            if not EMAIL_REGEX.match(raw_email):
                invalid_entry = {
                    'row': row_number + 1,
                    'email': raw_email,
                    'name': student_name or '[None]',
                    'reason': 'Malformed email syntax (invalid domain or format)'
                }
                invalid_rows.append(invalid_entry)
                row_number += 1
                continue

            # Rule 3: Case-insensitive duplicate detection
            normalized_email = raw_email.lower()
            if normalized_email in seen_emails:
                dup_entry = {
                    'row': row_number + 1,
                    'email': raw_email,
                    'name': student_name or '[None]',
                    'reason': 'Duplicate email address (first valid occurrence preserved)'
                }
                duplicate_rows.append(dup_entry)
            else:
                seen_emails.add(normalized_email)
                valid_recipients.append({
                    'row': row_number + 1,
                    'email': normalized_email,
                    'original_email': raw_email,
                    'name': student_name or '',
                    'source': 'csv'
                })

            row_number += 1

        if total_data_rows == 0:
            return {
                'success': False,
                'error': 'The CSV file contains a header but no student data rows.',
                'code': 'NO_DATA_ROWS'
            }

        return {
            'success': True,
            'filename': filename,
            'total_data_rows': total_data_rows,
            'valid_unique_count': len(valid_recipients),
            'duplicate_count': len(duplicate_rows),
            'invalid_count': len(invalid_rows) - len(blank_rows), # Malformed syntax count
            'blank_count': len(blank_rows),
            'total_rejected_count': len(duplicate_rows) + len(invalid_rows),
            'valid_recipients': valid_recipients,
            'duplicate_rows': duplicate_rows,
            'invalid_rows': invalid_rows, # contains both malformed and blank with clear reasons
            'summary_message': (
                f"Successfully parsed {total_data_rows} row(s): {len(valid_recipients)} valid unique recipient(s), "
                f"{len(duplicate_rows)} duplicate(s) removed, {len(invalid_rows)} invalid/blank row(s)."
            )
        }

    except Exception as exc:
        return {
            'success': False,
            'error': f'Failed to parse CSV file: {str(exc)}',
            'code': 'MALFORMED_CSV'
        }
