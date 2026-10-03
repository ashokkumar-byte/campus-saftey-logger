import os
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import app, create_default_management, ensure_database_upgrade
import backend.models.report_model as report_model
import backend.routes.report_routes as report_routes


class ReportWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "workflow.db")
        connection = sqlite3.connect(self.database_path)
        schema = Path("database/schema.sql").read_text(encoding="utf-8")
        connection.executescript(schema)
        connection.executemany(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            [
                ("Test Student", "student@example.com", generate_password_hash("secret123"), "student"),
                ("Test Management", "management@example.com", generate_password_hash("secret123"), "management"),
                ("Other Student", "other@example.com", generate_password_hash("secret123"), "student"),
            ],
        )
        connection.commit()
        connection.close()

        self.user_database_patch = patch("backend.models.user_model.DATABASE_PATH", self.database_path)
        self.report_database_patch = patch("backend.models.report_model.DATABASE_PATH", self.database_path)
        self.upload_folder = os.path.join(self.temp_dir.name, "evidence")
        os.makedirs(self.upload_folder)
        self.upload_folder_patch = patch.object(report_routes, "UPLOAD_FOLDER", self.upload_folder)
        self.user_database_patch.start()
        self.report_database_patch.start()
        self.upload_folder_patch.start()
        app.config["TESTING"] = True
        self.student = app.test_client()
        self.management = app.test_client()
        self.other_student = app.test_client()
        for client, user_id in ((self.student, 1), (self.management, 2), (self.other_student, 3)):
            with client.session_transaction() as session:
                session["user_id"] = user_id

    def tearDown(self):
        self.user_database_patch.stop()
        self.report_database_patch.stop()
        self.upload_folder_patch.stop()
        self.temp_dir.cleanup()

    def submit_report(self):
        return self.student.post(
            "/api/reports",
            data={
                "title": "North Hall lighting hazard",
                "description": "The stairwell is dark after sunset.",
                "category": "Safety",
                "incident_type": "Lighting defect",
                "campus_location": "North Hall",
                "building_area": "Second floor stairwell",
                "incident_date": "2026-09-30",
                "incident_time": "18:30",
                "severity": "High",
                "urgency": "Immediate",
                "people_involved": "Students passing through",
                "witnesses": "None known",
                "immediate_danger": "Yes",
                "injury_involved": "No",
                "emergency_assistance_required": "No",
                "contact_preference": "Email",
                "additional_details": "Please inspect the stairwell lighting.",
                "evidence": (BytesIO(b"workflow evidence"), "stairwell.jpg"),
            },
            content_type="multipart/form-data",
        )

    def test_student_management_student_lifecycle_persists(self):
        submitted = self.submit_report()
        self.assertEqual(submitted.status_code, 201, submitted.get_json())
        report = submitted.get_json()["report"]
        self.assertRegex(report["report_id"], r"^SR-\d{8}-[A-F0-9]{10}$")

        management_list = self.management.get("/api/reports").get_json()["reports"]
        self.assertEqual([item["id"] for item in management_list], [report["id"]])

        hidden_from_other_student = self.other_student.get(f"/api/reports/{report['id']}")
        self.assertEqual(hidden_from_other_student.status_code, 403)
        own_reports = self.other_student.get("/api/reports").get_json()["reports"]
        self.assertEqual(own_reports, [])

        update_payload = {
            "status": "Under Review",
            "assigned_department": "Campus Security",
            "assigned_staff": "Officer Test",
            "investigation_notes": "Inspection scheduled.",
            "action_details": "Temporary lighting installed.",
            "management_response": "We have received the report and assigned an officer.",
        }
        updated = self.management.post(f"/api/reports/{report['id']}/management", json=update_payload)
        self.assertEqual(updated.status_code, 200, updated.get_json())
        self.assertEqual(self.management.post(f"/api/reports/{report['id']}/management", json=update_payload).status_code, 200)

        resolved = self.management.patch(f"/api/reports/{report['id']}/status", json={"status": "Resolved"})
        self.assertEqual(resolved.status_code, 200, resolved.get_json())
        closed = self.management.patch(f"/api/reports/{report['id']}/status", json={"status": "Closed"})
        self.assertEqual(closed.status_code, 200, closed.get_json())

        student_detail = self.student.get(f"/api/reports/{report['id']}")
        self.assertEqual(student_detail.status_code, 200)
        detail = student_detail.get_json()
        self.assertEqual(detail["report"]["status"], "Closed")
        self.assertEqual(detail["report"]["action_details"], "Temporary lighting installed.")
        self.assertEqual(detail["report"]["assigned_department"], "Campus Security")
        self.assertEqual(len(detail["responses"]), 1)
        self.assertEqual(detail["responses"][0]["message"], update_payload["management_response"])
        self.assertEqual([entry["new_status"] for entry in detail["status_history"]], [
            "Submitted", "Under Review", "Resolved", "Closed"
        ])
        self.assertEqual(self.management.get("/api/reports").status_code, 200)

        connection = sqlite3.connect(self.database_path)
        persisted = connection.execute(
            "SELECT status, action_details, assigned_department FROM reports WHERE id = ?",
            (report["id"],),
        ).fetchone()
        response_count = connection.execute(
            "SELECT COUNT(*) FROM responses WHERE report_id = ?",
            (report["id"],),
        ).fetchone()[0]
        connection.close()
        self.assertEqual(persisted, ("Closed", "Temporary lighting installed.", "Campus Security"))
        self.assertEqual(response_count, 1)

    def test_management_only_updates_and_server_validation(self):
        submitted = self.submit_report()
        report_id = submitted.get_json()["report"]["id"]

        student_status_update = self.student.patch(
            f"/api/reports/{report_id}/status",
            json={"status": "Resolved"},
        )
        self.assertEqual(student_status_update.status_code, 403)

        invalid_update = self.student.post(
            "/api/reports",
            json={"title": "Missing required fields"},
        )
        self.assertEqual(invalid_update.status_code, 400)

        photo_optional = self.student.post(
            "/api/reports",
            json={
                "category": "Safety",
                "campus_location": "North Hall",
                "description": "A required-field check.",
                "severity": "Medium",
                "incident_datetime": "2026-09-30T14:45",
            },
        )
        self.assertEqual(photo_optional.status_code, 201)
        no_photo_report = photo_optional.get_json()["report"]
        self.assertEqual(no_photo_report["evidence_files"], [])
        self.assertRegex(no_photo_report["report_id"], r"^SR-\d{8}-[A-F0-9]{10}$")
        management_reports = self.management.get("/api/reports").get_json()["reports"]
        self.assertIn(no_photo_report["id"], [item["id"] for item in management_reports])

        invalid_management_status = self.management.patch(
            f"/api/reports/{report_id}/status",
            json={"status": "Not a valid status"},
        )
        self.assertEqual(invalid_management_status.status_code, 400)

    def test_unified_login_authenticates_and_routes_by_role(self):
        student_on_student_login = self.student.post(
            "/api/auth/login",
            json={"email": "student@example.com", "password": "secret123"},
        )
        self.assertEqual(student_on_student_login.status_code, 200)

        management_on_student_login = self.student.post(
            "/api/auth/login",
            json={"email": "management@example.com", "password": "secret123"},
        )
        self.assertEqual(management_on_student_login.status_code, 200)
        self.assertEqual(management_on_student_login.get_json()["user"]["role"], "management")

        student_on_management_login = self.other_student.post(
            "/api/auth/management-login",
            json={"email": "student@example.com", "password": "secret123"},
        )
        self.assertEqual(student_on_management_login.status_code, 200)
        self.assertEqual(student_on_management_login.get_json()["user"]["role"], "student")

        management_login = self.management.post(
            "/api/auth/management-login",
            json={"email": "management@example.com", "password": "secret123"},
        )
        self.assertEqual(management_login.status_code, 200)
        self.assertEqual(management_login.get_json()["user"]["role"], "management")

    def test_registered_student_photo_optional_management_close_readback(self):
        student = app.test_client()
        email = "new-student@example.com"
        registration = student.post(
            "/api/auth/register",
            json={"full_name": "New Student", "email": email, "password": "student-pass"},
        )
        self.assertEqual(registration.status_code, 201)
        self.assertEqual(student.get("/api/auth/me").status_code, 401)

        login = student.post(
            "/api/auth/login",
            json={"email": email, "password": "student-pass"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.get_json()["user"]["role"], "student")

        submission = student.post(
            "/api/reports",
            json={
                "category": "Safety",
                "campus_location": "East Residence",
                "description": "The exterior entry light is not working.",
                "severity": "High",
                "incident_datetime": "2026-09-30T20:15",
            },
        )
        self.assertEqual(submission.status_code, 201, submission.get_json())
        report = submission.get_json()["report"]
        self.assertEqual(report["evidence_files"], [])
        self.assertRegex(report["report_id"], r"^SR-\d{8}-[A-F0-9]{10}$")
        self.assertIn(report["id"], [item["id"] for item in self.management.get("/api/reports").get_json()["reports"]])

        management_login = self.management.post(
            "/api/auth/login",
            json={"email": "management@example.com", "password": "secret123"},
        )
        self.assertEqual(management_login.status_code, 200)
        self.assertEqual(management_login.get_json()["user"]["role"], "management")
        update = self.management.post(
            f"/api/reports/{report['id']}/management",
            json={
                "status": "Under Review",
                "assigned_department": "Campus Security",
                "assigned_staff": "Evening Officer",
                "investigation_notes": "The fixture has been inspected.",
                "management_response": "An officer is reviewing the entrance.",
                "action_details": "Temporary lighting was installed.",
            },
        )
        self.assertEqual(update.status_code, 200)
        for status in ("Resolved", "Closed"):
            status_update = self.management.patch(
                f"/api/reports/{report['id']}/status",
                json={"status": status},
            )
            self.assertEqual(status_update.status_code, 200)

        student_login = student.post(
            "/api/auth/login",
            json={"email": email, "password": "student-pass"},
        )
        self.assertEqual(student_login.status_code, 200)
        student_reports = student.get("/api/reports").get_json()["reports"]
        self.assertEqual([item["id"] for item in student_reports], [report["id"]])
        detail = student.get(f"/api/reports/{report['id']}").get_json()
        self.assertEqual(detail["report"]["status"], "Closed")
        self.assertEqual(detail["report"]["action_details"], "Temporary lighting was installed.")
        self.assertEqual(detail["report"]["assigned_department"], "Campus Security")
        self.assertEqual(detail["responses"][0]["message"], "An officer is reviewing the entrance.")
        self.assertEqual([entry["new_status"] for entry in detail["status_history"]], [
            "Submitted", "Under Review", "Resolved", "Closed"
        ])

    def test_six_field_submission_generates_id_and_is_visible_to_management(self):
        evidence_folder = os.path.join(self.temp_dir.name, "six-field-evidence")
        os.makedirs(evidence_folder)
        form = {
            "category": "Facilities",
            "campus_location": "Science Building",
            "description": "A corridor light is not working.",
            "severity": "Medium",
            "incident_datetime": "2026-09-30T14:45",
            "evidence": (BytesIO(b"photo content"), "corridor.jpg"),
        }

        with patch.object(report_routes, "UPLOAD_FOLDER", evidence_folder):
            response = self.student.post("/api/reports", data=form, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 201, response.get_json())
        report = response.get_json()["report"]
        self.assertRegex(report["report_id"], r"^SR-\d{8}-[A-F0-9]{10}$")
        self.assertEqual(report["title"], "Facilities report at Science Building")
        self.assertEqual(report["incident_date"], "2026-09-30")
        self.assertEqual(report["incident_time"], "14:45")
        self.assertEqual(report["urgency"], "Normal")
        self.assertEqual(report["incident_type"], "Facilities")
        self.assertEqual(len(report["evidence_files"]), 1)
        self.assertTrue(os.path.isfile(os.path.join(evidence_folder, report["evidence_files"][0])))

        management_reports = self.management.get("/api/reports").get_json()["reports"]
        self.assertIn(report["id"], [item["id"] for item in management_reports])

    def test_legacy_database_upgrade_preserves_related_records(self):
        path = os.path.join(self.temp_dir.name, "legacy.db")
        connection = sqlite3.connect(path)
        connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE reports (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                location TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                evidence_files TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE responses (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL, responder_id INTEGER NOT NULL, message TEXT NOT NULL);
            CREATE TABLE notifications (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, report_id INTEGER, message TEXT NOT NULL);
            CREATE TABLE report_status_history (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL, old_status TEXT, new_status TEXT NOT NULL, changed_by INTEGER NOT NULL, notes TEXT);
            INSERT INTO users VALUES (1, 'Student', 'legacy@example.com', 'hash', 'student', 1);
            INSERT INTO users VALUES (2, 'Manager', 'legacy-manager@example.com', 'hash', 'management', 1);
            INSERT INTO reports (id, title, description, category, severity, location, status, created_by)
                VALUES (7, 'Legacy report', 'Existing description', 'Safety', 'high', 'North Hall', 'in_progress', 1);
            INSERT INTO responses VALUES (4, 7, 2, 'Existing response');
            INSERT INTO notifications VALUES (9, 1, 7, 'Existing notification');
            INSERT INTO report_status_history VALUES (3, 7, 'pending', 'in_progress', 2, 'Existing note');
        """)
        connection.commit()
        connection.close()

        ensure_database_upgrade(path)
        ensure_database_upgrade(path)

        connection = sqlite3.connect(path)
        report = connection.execute(
            "SELECT id, report_id, student_id, campus_location, status FROM reports"
        ).fetchone()
        related_counts = connection.execute(
            "SELECT (SELECT COUNT(*) FROM responses), (SELECT COUNT(*) FROM notifications), (SELECT COUNT(*) FROM report_status_history)"
        ).fetchone()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        connection.close()
        self.assertEqual(report, (7, "SR-000007", 1, "North Hall", "Investigating"))
        self.assertEqual(related_counts, (1, 1, 1))
        self.assertEqual(integrity, "ok")

        with patch.object(report_model, "DATABASE_PATH", path):
            new_report = report_model.create_report(
                {
                    "title": "New legacy-compatible report",
                    "description": "Submitted after upgrade.",
                    "category": "Safety",
                    "incident_type": "Hazard",
                    "campus_location": "South Hall",
                    "incident_date": "2026-09-30",
                    "incident_time": "11:30",
                    "severity": "Medium",
                    "urgency": "Normal",
                },
                1,
            )
            report_model.update_report(
                new_report["id"],
                {"title": "Updated legacy-compatible report", "campus_location": "East Hall"},
            )
        connection = sqlite3.connect(path)
        legacy_aliases = connection.execute(
            "SELECT location, created_by FROM reports WHERE id = ?",
            (new_report["id"],),
        ).fetchone()
        connection.close()
        self.assertEqual(legacy_aliases, ("East Hall", 1))

    def test_management_bootstrap_does_not_reset_existing_credentials(self):
        path = os.path.join(self.temp_dir.name, "management.db")
        connection = sqlite3.connect(path)
        connection.executescript(Path("database/schema.sql").read_text(encoding="utf-8"))
        password_hash = generate_password_hash("existing-password")
        connection.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("Existing Management", "management@example.org", password_hash, "management"),
        )
        connection.commit()
        connection.close()

        create_default_management(path)

        connection = sqlite3.connect(path)
        accounts = connection.execute(
            "SELECT email, password_hash FROM users WHERE role = 'management' ORDER BY email"
        ).fetchall()
        connection.close()
        self.assertIn(("management@example.org", password_hash), accounts)
        self.assertEqual(len(accounts), 2)
        with patch("backend.models.user_model.DATABASE_PATH", path):
            from backend.models.user_model import get_user_by_email
            from backend.services.auth_service import authenticate_user
            admin = authenticate_user("admin@123", "admin")
        self.assertEqual(admin["role"], "management")

    def test_evidence_upload_persists_and_requires_report_ownership(self):
        evidence_folder = os.path.join(self.temp_dir.name, "evidence-specific")
        os.makedirs(evidence_folder)
        form = {
            "title": "Evidence test report",
            "description": "An image is attached to this report.",
            "category": "Safety",
            "incident_type": "Hazard",
            "campus_location": "Library",
            "incident_date": "2026-09-30",
            "incident_time": "12:00",
            "severity": "Medium",
            "urgency": "Normal",
            "evidence": (BytesIO(b"test image bytes"), "hallway.png"),
        }

        with patch.object(report_routes, "UPLOAD_FOLDER", evidence_folder):
            submitted = self.student.post("/api/reports", data=form, content_type="multipart/form-data")
            self.assertEqual(submitted.status_code, 201, submitted.get_json())
            report = submitted.get_json()["report"]
            filename = report["evidence_files"][0]
            self.assertTrue(os.path.isfile(os.path.join(evidence_folder, filename)))

            own_download = self.student.get(f"/api/reports/{report['id']}/evidence/{filename}")
            self.assertEqual(own_download.status_code, 200)
            downloaded_bytes = own_download.data
            own_download.close()
            self.assertEqual(downloaded_bytes, b"test image bytes")

            forbidden_download = self.other_student.get(f"/api/reports/{report['id']}/evidence/{filename}")
            self.assertEqual(forbidden_download.status_code, 403)

            invalid_form = {**form, "evidence": (BytesIO(b"not an image"), "notes.txt")}
            invalid_upload = self.student.post("/api/reports", data=invalid_form, content_type="multipart/form-data")
            self.assertEqual(invalid_upload.status_code, 400)


if __name__ == "__main__":
    unittest.main()