import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash

from app import app, create_default_management
import backend.models.user_model as user_model


class AuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.temp_dir.name, "auth.db")
        connection = sqlite3.connect(database_path)
        connection.executescript(Path("database/schema.sql").read_text(encoding="utf-8"))
        connection.close()
        self.database_patch = patch.object(user_model, "DATABASE_PATH", database_path)
        self.database_patch.start()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_registration_success_message_and_no_auto_login(self):
        email = f"newuser_{uuid.uuid4().hex}@example.com"
        response = self.client.post(
            "/api/auth/register",
            json={
                "full_name": "Test User",
                "email": email,
                "password": "secret123",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["message"], "Registration successful")

        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

        login = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "secret123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.get_json()["user"]["role"], "student")

    def test_login_page_route_loads(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("Campus Safety Logger", page)
        self.assertNotIn("Management Login", page)
        response.close()

    def test_management_login_alias_redirects_to_the_single_login_page(self):
        response = self.client.get("/management/login")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        response.close()

    def test_management_dashboard_and_page_file_require_login(self):
        for path in ("/management", "/management/dashboard", "/pages/management.html"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], "/login", path)
            response.close()

    def test_unified_login_redirects_by_role_and_protects_pages(self):
        connection = sqlite3.connect(user_model.DATABASE_PATH)
        connection.execute(
            "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,1)",
            ("Test Student", "student@example.com", generate_password_hash("student-pass"), "student"),
        )
        connection.commit()
        connection.close()
        create_default_management(user_model.DATABASE_PATH)

        manager_login = self.client.post(
            "/api/auth/login",
            json={"email": "admin@123", "password": "admin"},
        )
        self.assertEqual(manager_login.status_code, 200)
        self.assertEqual(manager_login.get_json()["user"]["role"], "management")
        manager_dashboard = self.client.get("/management/dashboard")
        self.assertEqual(manager_dashboard.status_code, 200)
        self.assertIn(b"Management Dashboard", manager_dashboard.data)
        manager_dashboard.close()
        student_page_blocked = self.client.get("/reports")
        self.assertEqual(student_page_blocked.status_code, 302)
        self.assertEqual(student_page_blocked.headers["Location"], "/management/dashboard")

        self.client.post("/api/auth/logout")
        student_login = self.client.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "student-pass"},
        )
        self.assertEqual(student_login.status_code, 200)
        self.assertEqual(student_login.get_json()["user"]["role"], "student")
        student_dashboard = self.client.get("/dashboard")
        self.assertEqual(student_dashboard.status_code, 200)
        student_dashboard.close()
        management_page_blocked = self.client.get("/management/dashboard")
        self.assertEqual(management_page_blocked.status_code, 302)
        self.assertEqual(management_page_blocked.headers["Location"], "/dashboard")


if __name__ == "__main__":
    unittest.main()
