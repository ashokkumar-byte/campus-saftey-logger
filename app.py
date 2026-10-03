import os, sqlite3
from contextlib import closing
from flask import Flask, redirect, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from config import SECRET_KEY, DATABASE_DIR, DATABASE_PATH, UPLOAD_FOLDER
from backend.models.user_model import get_user_by_id
from backend.routes.auth_routes import auth_bp
from backend.routes.report_routes import report_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
PAGES_DIR = os.path.join(FRONTEND_DIR, "pages")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

def initialize_database():
    os.makedirs(DATABASE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    if not os.path.exists(DATABASE_PATH):
        with closing(sqlite3.connect(DATABASE_PATH)) as connection:
            with open(os.path.join(DATABASE_DIR, "schema.sql"), encoding="utf-8") as f:
                connection.executescript(f.read())


def ensure_database_upgrade(database_path=DATABASE_PATH):
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "users" not in tables:
            connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        if "reports" not in tables:
            with open(os.path.join(DATABASE_DIR, "schema.sql"), encoding="utf-8") as f:
                connection.executescript(f.read())

        reports_columns = {row[1] for row in connection.execute("PRAGMA table_info(reports)").fetchall()}
        additions = {
            "report_id": "ALTER TABLE reports ADD COLUMN report_id TEXT",
            "student_id": "ALTER TABLE reports ADD COLUMN student_id INTEGER",
            "incident_type": "ALTER TABLE reports ADD COLUMN incident_type TEXT",
            "campus_location": "ALTER TABLE reports ADD COLUMN campus_location TEXT",
            "building_area": "ALTER TABLE reports ADD COLUMN building_area TEXT",
            "incident_date": "ALTER TABLE reports ADD COLUMN incident_date TEXT",
            "incident_time": "ALTER TABLE reports ADD COLUMN incident_time TEXT",
            "urgency": "ALTER TABLE reports ADD COLUMN urgency TEXT",
            "people_involved": "ALTER TABLE reports ADD COLUMN people_involved TEXT",
            "witnesses": "ALTER TABLE reports ADD COLUMN witnesses TEXT",
            "immediate_danger": "ALTER TABLE reports ADD COLUMN immediate_danger INTEGER DEFAULT 0",
            "injury_involved": "ALTER TABLE reports ADD COLUMN injury_involved INTEGER DEFAULT 0",
            "emergency_assistance_required": "ALTER TABLE reports ADD COLUMN emergency_assistance_required INTEGER DEFAULT 0",
            "contact_preference": "ALTER TABLE reports ADD COLUMN contact_preference TEXT",
            "additional_details": "ALTER TABLE reports ADD COLUMN additional_details TEXT",
            "assigned_department": "ALTER TABLE reports ADD COLUMN assigned_department TEXT",
            "assigned_staff": "ALTER TABLE reports ADD COLUMN assigned_staff TEXT",
            "investigation_notes": "ALTER TABLE reports ADD COLUMN investigation_notes TEXT",
            "management_response": "ALTER TABLE reports ADD COLUMN management_response TEXT",
            "action_details": "ALTER TABLE reports ADD COLUMN action_details TEXT",
        }
        for name, statement in additions.items():
            if name not in reports_columns:
                connection.execute(statement)
                reports_columns.add(name)

        if "location" in reports_columns:
            connection.execute("UPDATE reports SET campus_location = location WHERE campus_location IS NULL AND location IS NOT NULL")
        if "created_by" in reports_columns:
            connection.execute("UPDATE reports SET student_id = created_by WHERE student_id IS NULL AND created_by IS NOT NULL")
        connection.execute("UPDATE reports SET report_id = 'SR-' || printf('%06d', id) WHERE report_id IS NULL OR TRIM(report_id) = ''")
        connection.execute("UPDATE reports SET contact_preference = 'Email' WHERE contact_preference IS NULL")
        connection.execute("UPDATE reports SET immediate_danger = 0 WHERE immediate_danger IS NULL")
        connection.execute("UPDATE reports SET injury_involved = 0 WHERE injury_involved IS NULL")
        connection.execute("UPDATE reports SET emergency_assistance_required = 0 WHERE emergency_assistance_required IS NULL")
        connection.execute("UPDATE reports SET status = 'Submitted' WHERE LOWER(status) = 'pending'")
        connection.execute("UPDATE reports SET status = 'Investigating' WHERE LOWER(status) = 'in_progress'")
        connection.execute("UPDATE reports SET status = 'Closed' WHERE LOWER(status) = 'rejected'")
        connection.execute("UPDATE reports SET severity = 'Critical' WHERE LOWER(severity) = 'critical'")
        connection.execute("UPDATE reports SET severity = 'High' WHERE LOWER(severity) = 'high'")
        connection.execute("UPDATE reports SET severity = 'Medium' WHERE LOWER(severity) = 'medium'")
        connection.execute("UPDATE reports SET severity = 'Low' WHERE LOWER(severity) = 'low'")
        connection.execute("UPDATE reports SET urgency = 'Immediate' WHERE LOWER(urgency) = 'immediate'")
        connection.execute("UPDATE reports SET urgency = 'High' WHERE LOWER(urgency) = 'high'")
        connection.execute("UPDATE reports SET urgency = 'Normal' WHERE LOWER(urgency) = 'normal'")
        connection.execute("UPDATE reports SET urgency = 'Low' WHERE LOWER(urgency) = 'low'")
        history_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='report_status_history'"
        ).fetchone()
        if history_table:
            for previous, current in (("pending", "Submitted"), ("in_progress", "Investigating"), ("resolved", "Resolved"), ("rejected", "Closed")):
                connection.execute("UPDATE report_status_history SET old_status = ? WHERE LOWER(old_status) = ?", (current, previous))
                connection.execute("UPDATE report_status_history SET new_status = ? WHERE LOWER(new_status) = ?", (current, previous))
        seen_report_ids = set()
        for row in connection.execute("SELECT id, report_id FROM reports ORDER BY id").fetchall():
            candidate = str(row[1] or "").strip()
            if not candidate or candidate in seen_report_ids:
                candidate = f"SR-{row[0]:06d}"
                while candidate in seen_report_ids:
                    candidate = f"{candidate}-{row[0]}"
                connection.execute("UPDATE reports SET report_id = ? WHERE id = ?", (candidate, row[0]))
            seen_report_ids.add(candidate)
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_reports_report_id ON reports(report_id)")
        with open(os.path.join(DATABASE_DIR, "schema.sql"), encoding="utf-8") as f:
            connection.executescript(f.read())
        connection.commit()


def create_default_management(database_path=DATABASE_PATH):
    with closing(sqlite3.connect(database_path)) as connection:
        exists = connection.execute(
            "SELECT id, password_hash, role, is_active FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1",
            ("admin@123",)
        ).fetchone()
        if not exists:
            connection.execute(
                "INSERT INTO users (full_name,email,password_hash,role,is_active) VALUES (?,?,?,?,?)",
                ("Campus Management", "admin@123", generate_password_hash("admin"), "management", 1)
            )
        elif exists[2] != "management" or not exists[3] or not check_password_hash(exists[1], "admin"):
            connection.execute(
                "UPDATE users SET full_name=?, password_hash=?, role='management', is_active=1 WHERE id=?",
                ("Campus Management", generate_password_hash("admin"), exists[0])
            )
        connection.commit()

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login")
def login_page():
    user = get_authenticated_page_user()
    if user:
        return redirect("/management/dashboard" if user["role"] == "management" else "/dashboard")
    return send_from_directory(PAGES_DIR, "login.html")

@app.route("/register")
def register_page():
    return send_from_directory(PAGES_DIR, "register.html")

@app.route("/dashboard")
def dashboard_page():
    return serve_role_page("dashboard.html", "student")

@app.route("/profile")
def profile_page():
    user = get_authenticated_page_user()
    if not user:
        return redirect("/login")
    return send_from_directory(PAGES_DIR, "profile.html")

@app.route("/management/profile")
def management_profile_page():
    user = get_authenticated_page_user()
    if not user:
        return redirect("/login")
    if user["role"] != "management":
        return redirect("/dashboard")
    return send_from_directory(PAGES_DIR, "profile.html")

@app.route("/reports")
def student_reports_page():
    return serve_role_page("student-reports.html", "student")

@app.route("/management")
def management_page():
    return management_dashboard_page()

@app.route("/management/login")
def management_login_page():
    return redirect("/login")

@app.route("/management/dashboard")
def management_dashboard_page():
    return serve_role_page("management.html", "management")


def get_authenticated_page_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    if not user or not user["is_active"]:
        session.clear()
        return None
    return user


def serve_role_page(filename, required_role):
    user = get_authenticated_page_user()
    if not user:
        return redirect("/login")
    if user["role"] != required_role:
        destination = "/management/dashboard" if user["role"] == "management" else "/dashboard"
        return redirect(destination)
    return send_from_directory(PAGES_DIR, filename)

@app.route("/<path:filename>")
def frontend_files(filename):
    if filename.startswith("pages/"):
        return redirect("/login")
    return send_from_directory(FRONTEND_DIR, filename)

app.register_blueprint(auth_bp)
app.register_blueprint(report_bp)

@app.errorhandler(404)
def not_found(error):
    return {"success": False, "message": "Resource not found."}, 404

@app.errorhandler(413)
def file_too_large(error):
    return {"success": False, "message": "Uploaded file is too large. Maximum size is 5 MB."}, 413

initialize_database()
ensure_database_upgrade()
create_default_management()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
