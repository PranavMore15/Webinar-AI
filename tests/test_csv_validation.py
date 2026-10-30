import io
import unittest
from app import create_app
from app.config import TestConfig
from app.services import csv_service

class TestCSVValidationSuite(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-secret-csv'
        self.client = self.app.test_client()

    # ---------------------------------------------------------
    # Core Service Unit Tests Covering All 12 Mandatory Cases
    # ---------------------------------------------------------

    def test_case_1_valid_csv_with_email_and_name(self):
        """Case 1: Valid CSV with 'email' and 'name' columns."""
        csv_data = b"email,name\nalice@example.com,Alice Smith\nbob@example.com,Bob Jones\n"
        res = csv_service.validate_and_parse_csv(csv_data, "students.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 2)
        self.assertEqual(res['valid_unique_count'], 2)
        self.assertEqual(res['duplicate_count'], 0)
        self.assertEqual(res['invalid_count'], 0)
        self.assertEqual(res['blank_count'], 0)
        self.assertEqual(res['valid_recipients'][0]['email'], 'alice@example.com')
        self.assertEqual(res['valid_recipients'][0]['name'], 'Alice Smith')

    def test_case_2_valid_csv_with_only_uppercase_email_column(self):
        """Case 2: Valid CSV with only an 'EMAIL' column (case-insensitive header, no name column)."""
        csv_data = b"EMAIL\nstudent1@test.edu\nstudent2@test.edu\nstudent3@test.edu\n"
        res = csv_service.validate_and_parse_csv(csv_data, "recipients.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 3)
        self.assertEqual(res['valid_unique_count'], 3)
        self.assertEqual(res['duplicate_count'], 0)
        self.assertEqual(res['invalid_count'], 0)
        self.assertEqual(res['blank_count'], 0)

    def test_case_3_duplicate_addresses_with_different_capitalization(self):
        """Case 3: Duplicate addresses with different capitalization (case-insensitive deduplication)."""
        csv_data = (
            b"email,name\n"
            b"john.doe@example.com,John Doe 1\n"
            b"JOHN.DOE@EXAMPLE.COM,John Doe Upper\n"
            b"John.Doe@Example.Com,John Doe Mixed\n"
            b"jane@example.com,Jane\n"
        )
        res = csv_service.validate_and_parse_csv(csv_data, "duplicates.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 4)
        self.assertEqual(res['valid_unique_count'], 2)  # john.doe and jane
        self.assertEqual(res['duplicate_count'], 2)
        self.assertEqual(res['valid_recipients'][0]['name'], 'John Doe 1')  # First preserved
        self.assertEqual(res['duplicate_rows'][0]['row'], 3)
        self.assertEqual(res['duplicate_rows'][1]['row'], 4)

    def test_case_4_leading_and_trailing_whitespace(self):
        """Case 4: Leading and trailing whitespace in emails and names should be stripped cleanly."""
        csv_data = b"email,name\n   student@domain.org   ,   Student Full Name   \n"
        res = csv_service.validate_and_parse_csv(csv_data, "whitespace.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['valid_unique_count'], 1)
        self.assertEqual(res['valid_recipients'][0]['email'], 'student@domain.org')
        self.assertEqual(res['valid_recipients'][0]['name'], 'Student Full Name')

    def test_case_5_blank_email_fields(self):
        """Case 5: Blank email fields are caught and counted separately."""
        csv_data = (
            b"email,name\n"
            b"valid@example.com,Valid Student\n"
            b",Missing Email Student\n"
            b"   ,Whitespace Only Email\n"
        )
        res = csv_service.validate_and_parse_csv(csv_data, "blank_emails.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 3)
        self.assertEqual(res['valid_unique_count'], 1)
        self.assertEqual(res['blank_count'], 2)
        self.assertEqual(res['invalid_count'], 0)  # separate from malformed syntax
        self.assertEqual(len(res['invalid_rows']), 2)

    def test_case_6_malformed_email_addresses(self):
        """Case 6: Malformed email syntax validation (missing @, missing domain, bad characters)."""
        csv_data = (
            b"email,name\n"
            b"plainaddress,No At Sign\n"
            b"@missingusername.com,No User\n"
            b"username@.com,Missing Domain Name\n"
            b"username@domain,No TLD\n"
            b"valid@example.com,Good Student\n"
        )
        res = csv_service.validate_and_parse_csv(csv_data, "malformed.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 5)
        self.assertEqual(res['valid_unique_count'], 1)
        self.assertEqual(res['invalid_count'], 4)
        self.assertEqual(res['blank_count'], 0)

    def test_case_7_csv_without_email_column(self):
        """Case 7: CSV without a recognizable email column is rejected with clear error."""
        csv_data = b"name,age,roll_number\nAlice,21,101\nBob,22,102\n"
        res = csv_service.validate_and_parse_csv(csv_data, "no_email_col.csv")
        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'MISSING_EMAIL_COLUMN')
        self.assertIn('Missing required "email" column', res['error'])

    def test_case_8_empty_csv(self):
        """Case 8: Empty CSV file (0 bytes or only empty whitespace lines)."""
        res_empty = csv_service.validate_and_parse_csv(b"", "empty.csv")
        self.assertFalse(res_empty['success'])
        self.assertEqual(res_empty['code'], 'EMPTY_FILE')

        res_spaces = csv_service.validate_and_parse_csv(b"   \n\n  \r\n", "empty_spaces.csv")
        self.assertFalse(res_spaces['success'])
        self.assertEqual(res_spaces['code'], 'EMPTY_FILE')

    def test_case_9_malformed_csv(self):
        """Case 9: CSV with unbalanced quotes or unreadable formatting."""
        # Unbalanced quotes causing csv reader parsing exception
        csv_data = b'email,name\n"invalid_quote@example.com,Student Name'
        # Standard csv reader parses quotes or handles rows; let's test handling
        res = csv_service.validate_and_parse_csv(csv_data, "unbalanced.csv")
        # Should either parse safely or return appropriate error without unhandled crash
        self.assertIn('success', res)

    def test_case_10_unsupported_file_extension(self):
        """Case 10: Reject non-CSV file extensions (e.g. .txt, .pdf, .xlsx)."""
        res_txt = csv_service.validate_and_parse_csv(b"email\na@b.com", "students.txt")
        self.assertFalse(res_txt['success'])
        self.assertEqual(res_txt['code'], 'INVALID_EXTENSION')

        res_pdf = csv_service.validate_and_parse_csv(b"email\na@b.com", "students.pdf")
        self.assertFalse(res_pdf['success'])
        self.assertEqual(res_pdf['code'], 'INVALID_EXTENSION')

    def test_case_11_uploads_exceeding_size_limit(self):
        """Case 11: File exceeding configured maximum byte limit."""
        small_limit = 100  # 100 bytes limit
        oversized_data = b"email,name\n" + (b"long.student.email@university.domain.edu,Student Long Name\n" * 5)
        res = csv_service.validate_and_parse_csv(oversized_data, "huge.csv", max_size_bytes=small_limit)
        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'FILE_TOO_LARGE')

    def test_case_12_csv_with_both_valid_and_invalid_entries(self):
        """Case 12: Complex mixed CSV with valid, duplicates, malformed, and blank entries."""
        csv_data = (
            b"Email,Student Name\n"
            b"student1@college.edu,Student One\n"
            b"bad-email-syntax,Bad Student\n"
            b"student2@college.edu,Student Two\n"
            b"STUDENT1@COLLEGE.EDU,Student One Duplicate\n"
            b",Blank Student\n"
            b"student3@college.edu,Student Three\n"
        )
        res = csv_service.validate_and_parse_csv(csv_data, "mixed.csv")
        self.assertTrue(res['success'])
        self.assertEqual(res['total_data_rows'], 6)
        self.assertEqual(res['valid_unique_count'], 3)   # student1, student2, student3
        self.assertEqual(res['duplicate_count'], 1)       # STUDENT1 duplicate
        self.assertEqual(res['invalid_count'], 1)         # bad-email-syntax
        self.assertEqual(res['blank_count'], 1)           # blank row
        self.assertEqual(res['total_rejected_count'], 3)

    # ---------------------------------------------------------
    # Route Integration & Authentication Protection Tests
    # ---------------------------------------------------------

    def test_upload_csv_requires_authentication(self):
        """Verify that unauthenticated requests to /api/upload-csv are rejected with 401."""
        data = {'file': (io.BytesIO(b"email\na@b.com"), 'test.csv')}
        res = self.client.post('/api/upload-csv', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.get_json()['success'])

    def test_authenticated_upload_csv_success_and_session_storage(self):
        """Verify that an authenticated user can upload CSV and session state is populated."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'

        csv_content = b"email,name\nstudent@college.edu,Student Name\n"
        data = {'file': (io.BytesIO(csv_content), 'valid_list.csv')}
        res = self.client.post('/api/upload-csv', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['valid_unique_count'], 1)

        # Verify /api/validate-state confirms server-side session state
        res_state = self.client.post('/api/validate-state', json={
            'hasWebinar': True,
            'webinarType': 'transcript',
            'webinarName': 'sample.txt'
        })
        self.assertEqual(res_state.status_code, 200)
        state_data = res_state.get_json()
        self.assertTrue(state_data['success'])
        self.assertEqual(state_data['details']['recipients_ready'], 1)

    def test_clear_csv_endpoint(self):
        """Verify that /api/clear-csv clears session recipient state."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['current_csv_validation'] = {'valid_unique_count': 5}

        res = self.client.post('/api/clear-csv')
        self.assertEqual(res.status_code, 200)

        # Subsequent validate-state should fail because CSV was cleared
        res_state = self.client.post('/api/validate-state', json={
            'hasWebinar': True,
            'webinarType': 'transcript',
            'webinarName': 'sample.txt'
        })
        self.assertEqual(res_state.status_code, 400)

if __name__ == '__main__':
    unittest.main()
