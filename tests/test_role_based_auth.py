"""
Role-Based Access Control and Authentication Test Suite for WebinarAI.
Verifies strict role separation:
1. Admin credentials work only through Admin Login.
2. Admin credentials are rejected through User Login.
3. User credentials work only through User Login.
4. User credentials are rejected through Admin Login.
5. Newly registered users strictly receive the 'user' role on the server.
6. Regular users cannot access admin routes or another user's records.
7. Admin safeguards (prevent self-deactivation and last admin deactivation).
8. Existing administrator account and database models remain intact.
"""

import unittest
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient

class TestRoleBasedAuth(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = self.app.test_client()

        # Seed test administrator and regular user
        self.admin = User(username='sysadmin', email='admin@test.org', role='admin', is_active=True)
        self.admin.set_password('AdminSecure123!')

        self.user = User(username='teststudent', email='student@test.edu', role='user', is_active=True)
        self.user.set_password('StudentPass123!')

        self.deactivated_user = User(username='inactiveuser', email='inactive@test.edu', role='user', is_active=False)
        self.deactivated_user.set_password('InactivePass123!')

        db.session.add_all([self.admin, self.user, self.deactivated_user])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    # -------------------------------------------------------------------------
    # 1. Admin Credentials Work ONLY Through Admin Login
    # -------------------------------------------------------------------------
    def test_admin_credentials_work_through_admin_login(self):
        """Verify admin credentials succeed when signing in through Admin Login."""
        response = self.client.post('/login', data={
            'username': 'sysadmin',
            'password': 'AdminSecure123!',
            'login_type': 'admin'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('System Administration Console', html)
        self.assertIn('Welcome back, Administrator sysadmin!', html)

        # Verify session is populated with role='admin'
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.admin.id)
            self.assertEqual(sess.get('role'), 'admin')

    def test_admin_credentials_work_via_admin_login_endpoint(self):
        """Verify admin credentials succeed via /admin/login endpoint."""
        response = self.client.post('/admin/login', data={
            'username': 'sysadmin',
            'password': 'AdminSecure123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('System Administration Console', html)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('role'), 'admin')

    # -------------------------------------------------------------------------
    # 2. Admin Credentials Are REJECTED Through User Login
    # -------------------------------------------------------------------------
    def test_admin_credentials_rejected_through_user_login(self):
        """Verify entering admin credentials into User Login is strictly rejected with no session created."""
        response = self.client.post('/login', data={
            'username': 'sysadmin',
            'password': 'AdminSecure123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Administrator accounts must sign in via Admin Login', html)

        # Verify NO session was created
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))
            self.assertIsNone(sess.get('role'))

    def test_admin_credentials_rejected_through_default_login_without_type(self):
        """Verify admin credentials posted to /login with default form parameters are rejected."""
        response = self.client.post('/login', data={
            'username': 'sysadmin',
            'password': 'AdminSecure123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Administrator accounts must sign in via Admin Login', html)

        # Verify NO session was created
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))

    # -------------------------------------------------------------------------
    # 3. User Credentials Work ONLY Through User Login
    # -------------------------------------------------------------------------
    def test_user_credentials_work_through_user_login(self):
        """Verify regular user credentials succeed when signing in through User Login."""
        response = self.client.post('/login', data={
            'username': 'teststudent',
            'password': 'StudentPass123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Webinar Processing & Distribution Dashboard', html)
        self.assertIn('Welcome back, teststudent!', html)

        # Verify session is populated with role='user'
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('user_id'), self.user.id)
            self.assertEqual(sess.get('role'), 'user')

    def test_user_credentials_work_via_email_through_user_login(self):
        """Verify regular user can log in using their email address via User Login."""
        response = self.client.post('/login', data={
            'username': 'student@test.edu',
            'password': 'StudentPass123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Welcome back, teststudent!', response.get_data(as_text=True))

    # -------------------------------------------------------------------------
    # 4. User Credentials Are REJECTED Through Admin Login
    # -------------------------------------------------------------------------
    def test_user_credentials_rejected_through_admin_login(self):
        """Verify entering regular user credentials into Admin Login is strictly rejected with no session."""
        response = self.client.post('/login', data={
            'username': 'teststudent',
            'password': 'StudentPass123!',
            'login_type': 'admin'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('This account does not have administrator privileges', html)

        # Verify NO session was created
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))
            self.assertIsNone(sess.get('role'))

    def test_user_credentials_rejected_via_admin_login_endpoint(self):
        """Verify entering regular user credentials into /admin/login is rejected with no session."""
        response = self.client.post('/admin/login', data={
            'username': 'teststudent',
            'password': 'StudentPass123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('This account does not have administrator privileges', html)

        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))

    # -------------------------------------------------------------------------
    # 5. Registration Strictly Assigns 'user' Role On Server
    # -------------------------------------------------------------------------
    def test_registration_strictly_assigns_user_role(self):
        """Verify new registration assigns 'user' role even if client submits role='admin'."""
        response = self.client.post('/register', data={
            'username': 'adversarial_user',
            'email': 'adv@test.edu',
            'password': 'SecurePass123!',
            'confirm_password': 'SecurePass123!',
            'role': 'admin'  # Malicious attempt to elevate privileges
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verify in database
        created = User.query.filter_by(username='adversarial_user').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.role, 'user', "Server must strictly enforce 'user' role on registration.")
        self.assertTrue(created.is_active)
        self.assertFalse(created.is_admin)

    def test_registration_duplicate_username_rejected(self):
        """Verify duplicate username registration is rejected."""
        response = self.client.post('/register', data={
            'username': 'teststudent',
            'email': 'different@test.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('username is already registered', response.get_data(as_text=True).lower())

    def test_registration_duplicate_email_rejected(self):
        """Verify duplicate email registration is rejected."""
        response = self.client.post('/register', data={
            'username': 'different_name',
            'email': 'student@test.edu',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('email address is already registered', response.get_data(as_text=True).lower())

    def test_registration_password_mismatch_rejected(self):
        """Verify password confirmation mismatch is rejected."""
        response = self.client.post('/register', data={
            'username': 'mismatch_user',
            'email': 'mismatch@test.edu',
            'password': 'Password123!',
            'confirm_password': 'Different123!'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('passwords do not match', response.get_data(as_text=True).lower())

    # -------------------------------------------------------------------------
    # 6. Route Authorization & Cross-User Data Isolation
    # -------------------------------------------------------------------------
    def test_regular_user_denied_access_to_admin_routes(self):
        """Verify regular user is denied access to /admin/dashboard."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        response = self.client.get('/admin/dashboard', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Administrator privileges required', html)
        self.assertIn('Webinar Processing & Distribution Dashboard', html)

    def test_unauthenticated_user_denied_access_to_admin_routes(self):
        """Verify unauthenticated user attempting to access /admin/dashboard is redirected."""
        response = self.client.get('/admin/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.headers['Location'])

    def test_regular_user_denied_access_to_admin_api(self):
        """Verify regular user calling /admin/api/... receives 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        response = self.client.post(f'/admin/api/users/{self.user.id}/toggle-status')
        self.assertEqual(response.status_code, 403)
        self.assertIn('Administrator privileges required', response.get_json()['message'])

    def test_job_ownership_and_cross_user_isolation(self):
        """Verify User A cannot access User B's job, but Admin can inspect all jobs."""
        user_b = User(username='user_b', email='b@test.edu', role='user', is_active=True)
        user_b.set_password('Pass123!')
        db.session.add(user_b)
        db.session.commit()

        job_b = ProcessingJob(
            user_id=user_b.id,
            input_type='transcript',
            input_file_name='b_notes.txt',
            input_file_path='storage/uploads/b_notes.txt'
        )
        db.session.add(job_b)
        db.session.commit()

        # User A attempts to access User B's job via /api/jobs/<id>
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        res_unauthorized = self.client.get(f'/api/jobs/{job_b.id}')
        self.assertEqual(res_unauthorized.status_code, 403)
        self.assertIn('Access denied', res_unauthorized.get_json()['message'])

        # User B accesses their own job
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_b.id
            sess['username'] = user_b.username
            sess['role'] = 'user'

        res_authorized = self.client.get(f'/api/jobs/{job_b.id}')
        self.assertEqual(res_authorized.status_code, 200)
        self.assertEqual(res_authorized.get_json()['job']['input_file_name'], 'b_notes.txt')

        # Admin accesses User B's job via admin diagnostics endpoint
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        res_admin = self.client.get(f'/admin/api/jobs/{job_b.id}/details')
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.get_json()['job']['owner_username'], 'user_b')

    # -------------------------------------------------------------------------
    # 7. Account Status & Administrator Safeguards
    # -------------------------------------------------------------------------
    def test_admin_toggle_user_status(self):
        """Verify admin can activate and deactivate regular users."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        res1 = self.client.post(f'/admin/api/users/{self.user.id}/toggle-status')
        self.assertEqual(res1.status_code, 200)
        self.assertFalse(res1.get_json()['is_active'])

        res2 = self.client.post(f'/admin/api/users/{self.user.id}/toggle-status')
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()['is_active'])

    def test_admin_cannot_deactivate_self(self):
        """Verify an admin cannot deactivate their own active account."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        response = self.client.post(f'/admin/api/users/{self.admin.id}/toggle-status')
        self.assertEqual(response.status_code, 400)
        self.assertIn('cannot deactivate your own', response.get_json()['message'].lower())

    def test_admin_cannot_deactivate_last_admin(self):
        """Verify system prevents deactivating the sole remaining active admin."""
        admin2 = User(username='admin2', email='admin2@test.org', role='admin', is_active=True)
        admin2.set_password('Pass123!')
        db.session.add(admin2)
        db.session.commit()

        # Deactivate first admin -> 1 active admin remains
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin2.id
            sess['username'] = admin2.username
            sess['role'] = 'admin'

        res1 = self.client.post(f'/admin/api/users/{self.admin.id}/toggle-status')
        self.assertEqual(res1.status_code, 200)

        # Deactivating the last active admin (admin2) must be prevented
        res2 = self.client.post(f'/admin/api/users/{admin2.id}/toggle-status')
        self.assertEqual(res2.status_code, 400)

    def test_deactivated_account_rejected_in_both_logins(self):
        """Verify deactivated accounts are rejected in both User and Admin logins."""
        res_user = self.client.post('/login', data={
            'username': 'inactiveuser',
            'password': 'InactivePass123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertIn('account has been deactivated', res_user.get_data(as_text=True).lower())

        res_admin = self.client.post('/login', data={
            'username': 'inactiveuser',
            'password': 'InactivePass123!',
            'login_type': 'admin'
        }, follow_redirects=True)
        self.assertIn('account has been deactivated', res_admin.get_data(as_text=True).lower())

    def test_invalid_credentials_rejected(self):
        """Verify invalid passwords rejected without session."""
        response = self.client.post('/login', data={
            'username': 'teststudent',
            'password': 'WrongPassword123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Invalid credentials', response.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('user_id'))

    # -------------------------------------------------------------------------
    # 8. Strict Admin / User Role Separation & Workspace Denial
    # -------------------------------------------------------------------------
    def test_admin_denied_access_to_user_dashboard_page(self):
        """Verify admin user accessing /dashboard is redirected to /admin/dashboard with a warning."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        response = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.headers['Location'])

        # Follow redirect and verify flash message and admin console rendering
        redirected_response = self.client.get('/dashboard', follow_redirects=True)
        self.assertEqual(redirected_response.status_code, 200)
        html = redirected_response.get_data(as_text=True)
        self.assertIn('Administrators cannot access the processing workspace', html)
        self.assertIn('System Administration Console', html)

    def test_admin_denied_access_to_user_workspace_apis(self):
        """Verify admin role is forbidden (403) from accessing all workspace processing endpoints."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        endpoints = [
            ('POST', '/api/upload-webinar', {'json': {}}),
            ('POST', '/api/clear-webinar', {'json': {}}),
            ('POST', '/api/upload-csv', {'json': {}}),
            ('POST', '/api/clear-csv', {'json': {}}),
            ('POST', '/api/clear-recipients', {'json': {}}),
            ('POST', '/api/validate-state', {'json': {}}),
            ('POST', '/api/submit-job', {'json': {}}),
            ('GET', '/api/jobs/1', {}),
            ('GET', '/api/recipients', {}),
            ('POST', '/api/recipients/add', {'json': {'email': 'test@org.edu'}}),
            ('POST', '/api/recipients/remove', {'json': {'email': 'test@org.edu'}})
        ]

        for method, endpoint, kwargs in endpoints:
            if method == 'POST':
                res = self.client.post(endpoint, **kwargs)
            else:
                res = self.client.get(endpoint, **kwargs)
            self.assertEqual(res.status_code, 403, f"Endpoint {endpoint} did not return 403 for admin")
            data = res.get_json()
            self.assertFalse(data['success'])
            self.assertIn('Administrator accounts cannot access the processing workspace', data['message'])

    def test_admin_interface_does_not_render_workspace_buttons(self):
        """Verify admin dashboard and navbar do not display workspace buttons or links to administrators."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('Open Processing Workspace', html)
        self.assertNotIn('>Workspace<', html)
        self.assertIn('Admin Console', html)

    def test_user_can_access_workspace(self):
        """Verify regular user can access workspace and navbar shows Workspace link."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Webinar Processing & Distribution Dashboard', html)
        self.assertIn('Section A: Webinar Content', html)
        self.assertIn('Section B: Student Email List', html)
        self.assertIn('>Workspace<', html)
        self.assertNotIn('Admin Console', html)

    # -------------------------------------------------------------------------
    # 9. Manual Individual Email Entry & Recipient Management
    # -------------------------------------------------------------------------
    def test_manual_recipient_add_success_and_trim(self):
        """Verify adding a recipient manually with valid email and trimmed name."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        res = self.client.post('/api/recipients/add', json={
            'email': '  student1@test.edu  ',
            'name': '  John Doe  '
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['valid_unique_count'], 1)
        self.assertEqual(data['recipient']['email'], 'student1@test.edu')
        self.assertEqual(data['recipient']['original_email'], 'student1@test.edu')
        self.assertEqual(data['recipient']['name'], 'John Doe')
        self.assertEqual(data['recipient']['source'], 'manual')

        # Verify GET /api/recipients confirms active draft state
        res_get = self.client.get('/api/recipients')
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.get_json()['valid_unique_count'], 1)

    def test_manual_recipient_validation_errors(self):
        """Verify missing or invalid email formats are rejected with 400 Bad Request."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        # Missing email
        res1 = self.client.post('/api/recipients/add', json={'email': '', 'name': 'No Email'})
        self.assertEqual(res1.status_code, 400)
        self.assertIn('Email address is required', res1.get_json()['message'])

        # Invalid format
        res2 = self.client.post('/api/recipients/add', json={'email': 'invalid-email-string'})
        self.assertEqual(res2.status_code, 400)
        self.assertIn('Invalid email address format', res2.get_json()['message'])

    def test_manual_recipient_duplicate_detection_case_insensitive(self):
        """Verify case-insensitive duplicate email detection preserves first valid entry and rejects duplicate."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        # Add initial recipient
        res1 = self.client.post('/api/recipients/add', json={
            'email': 'student@university.edu',
            'name': 'Original Student'
        })
        self.assertEqual(res1.status_code, 200)

        # Attempt to add duplicate with uppercase characters
        res2 = self.client.post('/api/recipients/add', json={
            'email': 'STUDENT@UNIVERSITY.EDU',
            'name': 'Duplicate Student'
        })
        self.assertEqual(res2.status_code, 400)
        data2 = res2.get_json()
        self.assertFalse(data2['success'])
        self.assertIn('already in the recipient list', data2['message'])

        # Verify only 1 recipient is in session and original name preserved
        res_list = self.client.get('/api/recipients')
        recipients = res_list.get_json()['recipients']
        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0]['name'], 'Original Student')

    def test_cross_deduplication_manual_and_csv(self):
        """Verify cross-source deduplication between manual entries and CSV uploads."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        # 1. Add manual recipient
        res_manual = self.client.post('/api/recipients/add', json={
            'email': 'manual@univ.edu',
            'name': 'Manual User'
        })
        self.assertEqual(res_manual.status_code, 200)

        # 2. Upload CSV containing manual@univ.edu (duplicate) and csv_new@univ.edu (new)
        import io
        csv_bytes = b"email,name\nMANUAL@UNIV.EDU,CSV Duplicate\ncsv_new@univ.edu,CSV User\n"
        res_csv = self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(csv_bytes), 'students.csv')
        }, content_type='multipart/form-data')
        self.assertEqual(res_csv.status_code, 200)
        csv_data = res_csv.get_json()
        self.assertEqual(csv_data['duplicate_count'], 1)
        self.assertEqual(csv_data['valid_unique_count'], 2)  # manual@univ.edu + csv_new@univ.edu

        # 3. Attempt to manually add csv_new@univ.edu (should be rejected as duplicate)
        res_dup_manual = self.client.post('/api/recipients/add', json={
            'email': 'CSV_NEW@UNIV.EDU',
            'name': 'Another Duplicate'
        })
        self.assertEqual(res_dup_manual.status_code, 400)
        self.assertIn('already in the recipient list', res_dup_manual.get_json()['message'])

    def test_manual_recipient_removal(self):
        """Verify removing a recipient updates recipient count and list."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'

        # Add two recipients
        self.client.post('/api/recipients/add', json={'email': 'user1@test.edu', 'name': 'U1'})
        self.client.post('/api/recipients/add', json={'email': 'user2@test.edu', 'name': 'U2'})

        # Remove user1
        res_remove = self.client.post('/api/recipients/remove', json={'email': 'USER1@TEST.EDU'})
        self.assertEqual(res_remove.status_code, 200)
        data = res_remove.get_json()
        self.assertEqual(data['valid_unique_count'], 1)
        self.assertEqual(data['recipients'][0]['email'], 'user2@test.edu')

        # Remove nonexistent recipient returns 404
        res_nonexistent = self.client.post('/api/recipients/remove', json={'email': 'nobody@test.edu'})
        self.assertEqual(res_nonexistent.status_code, 404)

        # Clear all recipients
        res_clear = self.client.post('/api/clear-recipients')
        self.assertEqual(res_clear.status_code, 200)
        res_empty = self.client.get('/api/recipients')
        self.assertEqual(res_empty.get_json()['valid_unique_count'], 0)

    def test_manual_recipient_job_persistence_in_database(self):
        """Verify manual recipients and webinar file correctly persist ProcessingJob and JobRecipient records."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['username'] = self.user.username
            sess['role'] = 'user'
            # Synthetic verified webinar upload in session
            sess['current_webinar_upload'] = {
                'input_type': 'transcript',
                'original_filename': 'lecture_notes.txt',
                'safe_filename': 'test_lecture_notes.txt',
                'storage_path': 'storage/uploads/test_lecture_notes.txt',
                'file_size': 128,
                'file_extension': '.txt'
            }

        # Create dummy file on disk so validation passes
        import os
        os.makedirs('storage/uploads', exist_ok=True)
        dummy_path = 'storage/uploads/test_lecture_notes.txt'
        with open(dummy_path, 'w') as f:
            f.write("Quantum Physics Webinar Transcript Content")

        try:
            # Add two recipients manually
            self.client.post('/api/recipients/add', json={'email': 'student_a@test.edu', 'name': 'Student A'})
            self.client.post('/api/recipients/add', json={'email': 'student_b@test.edu', 'name': 'Student B'})

            # Pre-validation passes
            res_val = self.client.post('/api/validate-state', json={'hasWebinar': True})
            self.assertEqual(res_val.status_code, 200)
            self.assertEqual(res_val.get_json()['details']['recipients_ready'], 2)

            # Submit processing job
            res_submit = self.client.post('/api/submit-job', json={'title': 'Quantum Physics Job'})
            self.assertEqual(res_submit.status_code, 201)
            job_id = res_submit.get_json()['job']['id']

            # Query database
            job = db.session.get(ProcessingJob, job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job.user_id, self.user.id)
            self.assertEqual(job.total_recipients, 2)
            self.assertEqual(job.overall_status, 'ready')

            # Verify persisted recipients
            recipients = job.recipients.all()
            self.assertEqual(len(recipients), 2)
            emails = {r.email for r in recipients}
            self.assertEqual(emails, {'student_a@test.edu', 'student_b@test.edu'})
            for r in recipients:
                self.assertEqual(r.delivery_status, 'pending')

        finally:
            if os.path.exists(dummy_path):
                os.remove(dummy_path)

if __name__ == '__main__':
    unittest.main()

