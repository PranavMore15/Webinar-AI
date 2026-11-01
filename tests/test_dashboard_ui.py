import os
import subprocess
import unittest
from app import create_app
from app.config import TestConfig
from app.models import db, User

class TestDashboardUI(unittest.TestCase):
    """
    Automated tests verifying dashboard client-side UI script syntax,
    template structure, and multi-source panel accessibility.
    """
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-dashboard-ui-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        self.user = User(username='ui_tester', email='uitester@webinarai.edu', role='user', is_active=True)
        self.user.set_password('SecureUiPass123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'ui_tester'
            sess['role'] = 'user'

    def test_dashboard_js_syntax_clean(self):
        """Task 2.1: Verify app/static/js/dashboard.js parses cleanly without JavaScript syntax errors."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static', 'js', 'dashboard.js')
        self.assertTrue(os.path.exists(js_path), f"dashboard.js not found at {js_path}")

        # Run node --check to validate syntax
        result = subprocess.run(
            ['node', '--check', js_path],
            capture_output=True,
            text=True
        )
        self.assertEqual(
            result.returncode,
            0,
            f"dashboard.js syntax error detected:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    def test_dashboard_template_renders_all_source_panels_and_manual_mode(self):
        """Task 2.2: Verify Section A renders all 6 source options, manual format mode, and input controls."""
        self._login()
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # 1. Verify 6 Content Source radio buttons
        for mode_id in ['modeManual', 'modeDirect', 'modeYouTube', 'modeGDrive', 'modeLocalFile', 'modeLocalFolder']:
            self.assertIn(f'id="{mode_id}"', html, f"Missing radio button {mode_id}")
            self.assertIn(f'for="{mode_id}"', html, f"Missing label for {mode_id}")

        # 2. Verify Manual Format Mode section and dropzones
        self.assertIn('id="panelSourceManual"', html)
        self.assertIn('Manual Format Mode', html)
        self.assertIn('id="sourceTypeVideo"', html)
        self.assertIn('id="sourceTypeTranscript"', html)
        self.assertIn('id="videoUploadContainer"', html)
        self.assertIn('id="transcriptUploadContainer"', html)

        # 3. Verify YouTube Panel & Input Controls
        self.assertIn('id="panelSourceYouTube"', html)
        self.assertIn('id="youtubeUrlInput"', html)
        self.assertIn('id="btnCheckYouTubeAccessibility"', html)

        # 4. Verify Direct Link, GDrive, Local File/Folder Panels
        self.assertIn('id="panelSourceDirect"', html)
        self.assertIn('id="directMediaUrlInput"', html)
        self.assertIn('id="panelSourceGDrive"', html)
        self.assertIn('id="gdriveUrlInput"', html)
        self.assertIn('id="panelSourceLocalFile"', html)
        self.assertIn('id="localMediaFileInput"', html)
        self.assertIn('id="panelSourceLocalFolder"', html)
        self.assertIn('id="localFolderInput"', html)

    def test_dashboard_js_contains_source_mode_switching_and_autofocus(self):
        """Verify dashboard.js defines source panel switching with input autofocus."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static', 'js', 'dashboard.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('switchContentSourceMode', content)
        self.assertIn('youtubeUrlInput.focus()', content)
        self.assertIn('directMediaUrlInput.focus()', content)
        self.assertIn('gdriveUrlInput.focus()', content)
        self.assertIn('sourceSelectorGrid label', content)

    def test_dashboard_jobs_table_and_dynamic_row_helpers(self):
        """Verify Section C table structure and JavaScript row prepending helpers."""
        self._login()
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Check DOM elements for Section C table and empty state
        self.assertIn('id="recentJobsContainer"', html)
        self.assertIn('id="recentJobsTableBody"', html)
        self.assertIn('id="recentJobsCountBadge"', html)
        self.assertIn('id="jobEmptyState"', html)

        # Check JS helper functions
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'static', 'js', 'dashboard.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('function renderJobRowHtml', content)
        self.assertIn('function prependJobToTable', content)
        self.assertIn('prependJobToTable(result.job)', content)
        self.assertIn('updateJobTableRowFromData', content)


if __name__ == '__main__':
    unittest.main()

