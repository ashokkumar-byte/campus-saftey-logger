CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL UNIQUE,
    student_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Safety',
    incident_type TEXT NOT NULL DEFAULT 'Other',
    campus_location TEXT NOT NULL,
    building_area TEXT,
    incident_date TEXT,
    incident_time TEXT,
    severity TEXT NOT NULL DEFAULT 'medium',
    urgency TEXT NOT NULL DEFAULT 'normal',
    people_involved TEXT,
    witnesses TEXT,
    immediate_danger INTEGER NOT NULL DEFAULT 0,
    injury_involved INTEGER NOT NULL DEFAULT 0,
    emergency_assistance_required INTEGER NOT NULL DEFAULT 0,
    evidence_files TEXT DEFAULT '[]',
    contact_preference TEXT NOT NULL DEFAULT 'Email',
    additional_details TEXT,
    status TEXT NOT NULL DEFAULT 'Submitted',
    assigned_department TEXT,
    assigned_staff TEXT,
    investigation_notes TEXT,
    management_response TEXT,
    action_details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_reports_student_id ON reports(student_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_report_id ON reports(report_id);

CREATE TABLE IF NOT EXISTS report_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by INTEGER NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES reports(id),
    FOREIGN KEY (changed_by) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_report_status_history_report_id ON report_status_history(report_id);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    responder_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES reports(id),
    FOREIGN KEY (responder_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_responses_report_id ON responses(report_id);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    report_id INTEGER,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (report_id) REFERENCES reports(id)
);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
