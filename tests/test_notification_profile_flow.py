import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import app


class NotificationAndProfileFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "notifications_profile.db")
        connection = sqlite3.connect(self.database_path)
        schema = Path("database/schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.executemany(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            [
                ("Student User", "student@example.com", generate_password_hash("secret123"), "student"),
                ("Management User", "management@example.com", generate_password_hash("secret123"), "management"),
            ],
        )
        connection.commit()
        connection.close()

        self.user_patch = patch("backend.models.user_model.DATABASE_PATH", self.database_path)
        self.report_patch = patch("backend.models.report_model.DATABASE_PATH", self.database_path)
        self.user_patch.start()
        self.report_patch.start()

        app.config["TESTING"] = True
        self.student = app.test_client()
        self.management = app.test_client()
        with self.student.session_transaction() as session:
            session["user_id"] = 1
            session["role"] = "student"
        with self.management.session_transaction() as session:
            session["user_id"] = 2
            session["role"] = "management"

    def tearDown(self):
        self.user_patch.stop()
        self.report_patch.stop()
        self.temp_dir.cleanup()

    def test_notification_and_profile_workflow(self):
        report_response = self.student.post(
            "/api/reports",
            json={
                "category": "Safety",
                "campus_location": "North Hall",
                "description": "The entrance lighting is out.",
                "severity": "High",
                "incident_datetime": "2026-09-30T14:15",
            },
        )
        self.assertEqual(report_response.status_code, 201, report_response.get_json())
        report = report_response.get_json()["report"]

        management_notifications = self.management.get("/api/notifications").get_json()
        self.assertGreaterEqual(management_notifications["unread_count"], 1)
        self.assertTrue(any(item["report_id"] == report["id"] for item in management_notifications["notifications"]))

        notification = next(item for item in management_notifications["notifications"] if item["report_id"] == report["id"])
        read_response = self.management.post(f"/api/notifications/{notification['id']}/read")
        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_response.get_json()["notification"]["is_read"])

        update_response = self.management.post(
            f"/api/reports/{report['id']}/management",
            json={
                "status": "Under Review",
                "management_response": "An officer is reviewing the entrance lighting.",
                "action_details": "Temporary lighting was arranged.",
            },
        )
        self.assertEqual(update_response.status_code, 200)

        student_notifications = self.student.get("/api/notifications").get_json()
        self.assertTrue(any("Under Review" in item["message"] or "reviewing" in item["message"].lower() for item in student_notifications["notifications"]))
        self.assertIn("status changed to Under Review", student_notifications["notifications"][0]["message"])

        profile = self.student.get("/api/auth/profile").get_json()
        self.assertEqual(profile["user"]["email"], "student@example.com")

        updated_profile = self.student.patch(
            "/api/auth/profile",
            json={"full_name": "Student Updated"},
        )
        self.assertEqual(updated_profile.status_code, 200)
        self.assertEqual(self.student.get("/api/auth/profile").get_json()["user"]["full_name"], "Student Updated")

    def test_profile_rejects_invalid_email_and_duplicate_email(self):
        invalid_email = self.student.patch(
            "/api/auth/profile",
            json={"email": "not-an-email"},
        )
        self.assertEqual(invalid_email.status_code, 400)

        duplicate_email = self.student.patch(
            "/api/auth/profile",
            json={"email": "management@example.com"},
        )
        self.assertEqual(duplicate_email.status_code, 409)
