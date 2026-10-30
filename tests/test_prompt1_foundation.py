import unittest
from app import create_app
from app.config import TestConfig

class TestPrompt1Foundation(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()
        from app.models import db, User
        db.create_all()
        user = User(username='operator', email='operator@test.edu', role='user', is_active=True)
        user.set_password('OperatorPass123!')
        db.session.add(user)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        from app.models import db
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_root_redirects_to_login_when_unauthenticated(self):
        response = self.client.get('/', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_login_page_renders_successfully(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Sign In', html)
        self.assertIn('Username or Email', html)

    def test_login_post_and_dashboard_access(self):
        # Test standard user login into processing workspace
        response = self.client.post('/login', data={
            'username': 'operator',
            'password': 'OperatorPass123!',
            'login_type': 'user'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Webinar Processing & Distribution Dashboard', html)
        self.assertIn('Section A: Webinar Content', html)
        self.assertIn('Section B: Student Email List', html)
        self.assertIn('Section C: Processing Status & Job Lifecycle', html)
        self.assertIn('Start Processing & Deliver Email', html)

    def test_validate_state_endpoint_rejects_missing_inputs(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
        
        # Test missing webinar
        res = self.client.post('/api/validate-state', json={
            'hasWebinar': False,
            'recipientCount': 5
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])

        # Test missing recipients
        res2 = self.client.post('/api/validate-state', json={
            'hasWebinar': True,
            'webinarType': 'video',
            'webinarName': 'demo.mp4',
            'recipientCount': 0
        })
        self.assertEqual(res2.status_code, 400)
        data2 = res2.get_json()
        self.assertFalse(data2['success'])

    def test_validate_state_endpoint_accepts_valid_inputs(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'

        res = self.client.post('/api/validate-state', json={
            'hasWebinar': True,
            'webinarType': 'video',
            'webinarName': 'presentation.mp4',
            'recipientCount': 12
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['details']['recipients_ready'], 12)

    def test_logout(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            
        response = self.client.get('/logout', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

if __name__ == '__main__':
    unittest.main()
