"""
Stage 3 Authentication & Role-Based Authorization Verification Suite
-------------------------------------------------------------------
Verifies all 12 Acceptance Criteria:
  TEST 1:  Create an Organizer account -> password stored only as secure hash.
  TEST 2:  Create a Management account -> registration succeeds using admin code.
  TEST 2B: Prevent Unauthorized Management Registration (privilege escalation denied).
  TEST 3:  Login with valid Organizer credentials -> identified as Organizer.
  TEST 4:  Login with valid Management credentials -> identified as Management.
  TEST 5:  Login with incorrect password -> rejected with HTTP 401.
  TEST 6:  Access protected endpoint without logging in -> rejected with HTTP 401.
  TEST 7:  Login as Organizer and attempt Management endpoint -> rejected with HTTP 403.
  TEST 8:  Login as Management and access Management endpoint -> succeeds with HTTP 200.
  TEST 9:  Logout -> session terminated.
  TEST 10: Access protected endpoint after logout -> rejected with HTTP 401.
  TEST 11: Attempt to manipulate role from frontend/request -> server uses DB role.
  TEST 12: Verify that password hashes are NEVER returned in API responses.
"""

import sys
import unittest
import sqlite3
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app
from config.settings import settings
from config.db import check_db_status
import config.db
from middleware.auth import hash_password, verify_password


try:
    from tests.db_guard import IsolatedTestDatabase, install_global_safety_guard
except ImportError:
    from db_guard import IsolatedTestDatabase, install_global_safety_guard


class TestStage3Authentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure test database environment using an isolated in-memory test database."""
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SECRET_KEY'] = 'test-secret-key-for-stage3-verification'

        install_global_safety_guard()

        cls.isolated_db = IsolatedTestDatabase()
        cls.sqlite_conn = cls.isolated_db.init_database()
        cls.isolated_db.seed_baseline()
        cls.isolated_db.patch_models()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "isolated_db"):
            cls.isolated_db.restore_models()

    def setUp(self):
        self.client = self.app.test_client()

    # -------------------------------------------------------------
    # TEST 1: Register Organizer Account
    # -------------------------------------------------------------
    def test_01_register_organizer_account_hashes_password(self):
        """TEST 1: Create an Organizer account and verify password is stored only as secure hash."""
        payload = {
            "name": "New Test Organizer",
            "email": "new.organizer@college.edu",
            "password": "SecurePassword123",
            "role": "organizer"
        }
        res = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data['user']['email'], "new.organizer@college.edu")
        self.assertEqual(data['user']['role'], "organizer")
        self.assertNotIn('password_hash', data['user'])

        # Verify password is not plaintext in DB
        from models.user import UserModel
        user_in_db = UserModel.get_by_email("new.organizer@college.edu")
        self.assertIsNotNone(user_in_db)
        self.assertNotEqual(user_in_db['password_hash'], "SecurePassword123")
        self.assertTrue(verify_password("SecurePassword123", user_in_db['password_hash']))
        print("   [OK] TEST 1: Organizer registered and password securely hashed.")

    # -------------------------------------------------------------
    # TEST 2: Register Management Account with Secret Code
    # -------------------------------------------------------------
    def test_02_register_management_account_with_code(self):
        """TEST 2: Create a Management account with the development/admin authorization code."""
        payload = {
            "name": "New Dean Management",
            "email": "dean.mgmt@college.edu",
            "password": "ManagementPassword123",
            "role": "management",
            "management_code": settings.MANAGEMENT_REGISTRATION_CODE
        }
        res = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIn(data['user']['role'], ["administrator", "management"])
        print("   [OK] TEST 2: Administrator account created using valid authorization code.")

    # -------------------------------------------------------------
    # TEST 2B: Prevent Unauthorized Management Privilege Escalation
    # -------------------------------------------------------------
    def test_02b_prevent_unauthorized_management_registration(self):
        """TEST 2B: Attempting to register as management without valid code is rejected with 403."""
        payload = {
            "name": "Hacker User",
            "email": "hacker@college.edu",
            "password": "Password123",
            "role": "management",
            "management_code": "wrong_secret_code"
        }
        res = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn("denied", data.get("message", "").lower())
        print("   [OK] TEST 2B: Privilege escalation without valid code strictly rejected (403).")

    # -------------------------------------------------------------
    # TEST 3: Login with Valid Organizer Credentials
    # -------------------------------------------------------------
    def test_03_login_valid_organizer_credentials(self):
        """TEST 3: Login with valid Organizer credentials identifies as Organizer."""
        payload = {
            "email": "john.organizer@college.edu",
            "password": "Organizer@123"
        }
        res = self.client.post('/api/auth/login', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['user']['role'], "organizer")
        self.assertEqual(data['user']['email'], "john.organizer@college.edu")
        print("   [OK] TEST 3: Organizer login succeeded and role verified as 'organizer'.")

    # -------------------------------------------------------------
    # TEST 4: Login with Valid Management Credentials
    # -------------------------------------------------------------
    def test_04_login_valid_management_credentials(self):
        """TEST 4: Login with valid Management credentials identifies as Management."""
        payload = {
            "email": "admin@college.edu",
            "password": "Admin@123"
        }
        res = self.client.post('/api/auth/login', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['user']['role'], "management")
        print("   [OK] TEST 4: Management login succeeded and role verified as 'management'.")

    # -------------------------------------------------------------
    # TEST 5: Login with Incorrect Password
    # -------------------------------------------------------------
    def test_05_login_incorrect_password_fails(self):
        """TEST 5: Login with incorrect password fails with 401."""
        payload = {
            "email": "admin@college.edu",
            "password": "WrongPassword999!"
        }
        res = self.client.post('/api/auth/login', json=payload)
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn("Invalid", data.get("message", ""))
        print("   [OK] TEST 5: Login with incorrect password correctly rejected (401).")

    # -------------------------------------------------------------
    # TEST 6: Access Protected Endpoint Without Logging In
    # -------------------------------------------------------------
    def test_06_access_protected_endpoint_unauthenticated_fails(self):
        """TEST 6: Accessing protected endpoints without logging in returns 401."""
        # Test /api/auth/me
        res_me = self.client.get('/api/auth/me')
        self.assertEqual(res_me.status_code, 401)

        # Test /api/organizer/dashboard-data
        res_org = self.client.get('/api/organizer/dashboard-data')
        self.assertEqual(res_org.status_code, 401)

        # Test /api/management/dashboard-data
        res_mgmt = self.client.get('/api/management/dashboard-data')
        self.assertEqual(res_mgmt.status_code, 401)
        print("   [OK] TEST 6: Protected endpoints reject unauthenticated access (401).")

    # -------------------------------------------------------------
    # TEST 7: Organizer Attempting Access to Management-Only Endpoint
    # -------------------------------------------------------------
    def test_07_organizer_cannot_access_management_endpoint(self):
        """TEST 7: Login as Organizer and attempt to access Management endpoint -> 403 Forbidden."""
        # 1. Login as Organizer
        login_res = self.client.post('/api/auth/login', json={
            "email": "john.organizer@college.edu",
            "password": "Organizer@123"
        })
        self.assertEqual(login_res.status_code, 200)

        # 2. Access Organizer endpoint -> should succeed
        org_res = self.client.get('/api/organizer/dashboard-data')
        self.assertEqual(org_res.status_code, 200)

        # 3. Access Management endpoint -> must be forbidden (403)
        mgmt_res = self.client.get('/api/management/dashboard-data')
        self.assertEqual(mgmt_res.status_code, 403)
        data = mgmt_res.get_json()
        self.assertIn("Access denied", data.get("message", ""))
        print("   [OK] TEST 7: Organizer accessing management endpoint strictly forbidden (403).")

    # -------------------------------------------------------------
    # TEST 8: Management Accessing Management-Only Endpoint
    # -------------------------------------------------------------
    def test_08_management_can_access_management_endpoint(self):
        """TEST 8: Login as Management and access Management endpoint -> 200 OK."""
        login_res = self.client.post('/api/auth/login', json={
            "email": "admin@college.edu",
            "password": "Admin@123"
        })
        self.assertEqual(login_res.status_code, 200)

        mgmt_res = self.client.get('/api/management/dashboard-data')
        self.assertEqual(mgmt_res.status_code, 200)
        data = mgmt_res.get_json()
        self.assertEqual(data['role'], "management")
        print("   [OK] TEST 8: Management successfully accessed management endpoint (200).")

    # -------------------------------------------------------------
    # TEST 9 & 10: Logout and Post-Logout Protected Access
    # -------------------------------------------------------------
    def test_09_and_10_logout_clears_session_and_denies_access(self):
        """TEST 9 & 10: Logout clears session and subsequent protected requests are rejected."""
        # 1. Login
        self.client.post('/api/auth/login', json={
            "email": "admin@college.edu",
            "password": "Admin@123"
        })

        # Verify active session
        me_res1 = self.client.get('/api/auth/me')
        self.assertEqual(me_res1.status_code, 200)

        # 2. Logout (TEST 9)
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)
        print("   [OK] TEST 9: Logout endpoint executed successfully.")

        # 3. Post-logout attempt to access protected endpoint (TEST 10)
        me_res2 = self.client.get('/api/auth/me')
        self.assertEqual(me_res2.status_code, 401)

        mgmt_res = self.client.get('/api/management/dashboard-data')
        self.assertEqual(mgmt_res.status_code, 401)
        print("   [OK] TEST 10: Subsequent requests after logout rejected with 401.")

    # -------------------------------------------------------------
    # TEST 11: Attempt to Manipulate Role From Request Payload / Headers
    # -------------------------------------------------------------
    def test_11_role_manipulation_attempt_uses_database_role(self):
        """TEST 11: Backend strictly uses verified database role, ignoring client payload role."""
        # 1. Login as Organizer
        self.client.post('/api/auth/login', json={
            "email": "john.organizer@college.edu",
            "password": "Organizer@123"
        })

        # 2. Attempt to spoof 'management' role via query param, body, or header
        res = self.client.get(
            '/api/management/dashboard-data?role=management',
            headers={'X-User-Role': 'management'},
            json={'role': 'management'}
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn("Access denied", data.get("message", ""))
        self.assertIn("organizer", data.get("message", ""))
        print("   [OK] TEST 11: Role manipulation attempt thwarted; backend strictly enforces DB role.")

    # -------------------------------------------------------------
    # TEST 12: Password Hash Never Returned in Any API Response
    # -------------------------------------------------------------
    def test_12_password_hashes_never_returned_in_api_responses(self):
        """TEST 12: Ensure password_hash is omitted from register, login, me, and error responses."""
        # Check registration response
        reg_res = self.client.post('/api/auth/register', json={
            "name": "Audit User",
            "email": "audit.user@college.edu",
            "password": "PasswordAudit123!",
            "role": "organizer"
        })
        self.assertNotIn("password_hash", str(reg_res.get_data(as_text=True)))

        # Check login response
        login_res = self.client.post('/api/auth/login', json={
            "email": "audit.user@college.edu",
            "password": "PasswordAudit123!"
        })
        self.assertNotIn("password_hash", str(login_res.get_data(as_text=True)))

        # Check me response
        me_res = self.client.get('/api/auth/me')
        self.assertNotIn("password_hash", str(me_res.get_data(as_text=True)))
        print("   [OK] TEST 12: Verified password hashes are NEVER exposed in any API response.")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStage3Authentication)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
