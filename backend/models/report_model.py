import json
import sqlite3
import uuid
from datetime import datetime, timezone

from config import DATABASE_PATH


VALID_STATUSES = {
    "Submitted",
    "Under Review",
    "Assigned",
    "Investigating",
    "Action Taken",
    "Resolved",
    "Closed",
}


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _files_to_list(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return parsed
    return []


def _report_to_dict(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "report_id": row["report_id"],
        "student_id": row["student_id"],
        "student_name": row["student_name"],
        "student_email": row["student_email"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "campus_location": row["campus_location"],
        "incident_date": row["incident_date"],
        "incident_time": row["incident_time"],
        "severity": row["severity"],
        "evidence_files": _files_to_list(row["evidence_files"]),
        "status": row["status"],
        "management_response": row["management_response"],
        "action_details": row["action_details"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_report(data, student_id):
    payload = data or {}
    report_id = f"SR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:10].upper()}"
    category = str(payload.get("category", "Safety")).strip() or "Safety"
    campus_location = str(payload.get("campus_location", payload.get("location", ""))).strip()
    evidence_files = payload.get("evidence_files") or payload.get("evidence") or []
    if isinstance(evidence_files, str):
        evidence_files = [evidence_files]
    if isinstance(evidence_files, tuple):
        evidence_files = list(evidence_files)

    values = {
        "report_id": report_id,
        "student_id": student_id,
        "title": str(payload.get("title") or f"{category} report at {campus_location or 'Campus'}").strip(),
        "description": str(payload.get("description", "")).strip(),
        "category": category,
        "campus_location": campus_location,
        "incident_date": str(payload.get("incident_date", "")).strip(),
        "incident_time": str(payload.get("incident_time", "")).strip(),
        "severity": str(payload.get("severity", "Medium")).strip() or "Medium",
        "evidence_files": json.dumps(evidence_files),
        "status": "Submitted",
    }

    connection = get_connection()
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reports)").fetchall()}
        if "created_by" in columns:
            values["created_by"] = student_id
        if "location" in columns:
            values["location"] = values["campus_location"]
        insert_values = {key: value for key, value in values.items() if key in columns}
        cursor = connection.execute(
            f"INSERT INTO reports ({', '.join(insert_values)}) VALUES ({', '.join('?' for _ in insert_values)})",
            tuple(insert_values.values()),
        )
        connection.execute(
            "INSERT INTO report_status_history (report_id, old_status, new_status, changed_by, notes) VALUES (?, NULL, 'Submitted', ?, 'Report submitted')",
            (cursor.lastrowid, student_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT r.*, u.full_name AS student_name, u.email AS student_email FROM reports r LEFT JOIN users u ON u.id = r.student_id WHERE r.id = ? LIMIT 1",
            (cursor.lastrowid,),
        ).fetchone()
        return _report_to_dict(row)
    finally:
        connection.close()


def get_reports_for_user(student_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT r.*, u.full_name AS student_name, u.email AS student_email FROM reports r LEFT JOIN users u ON u.id = r.student_id WHERE r.student_id = ? ORDER BY r.created_at DESC",
            (student_id,),
        ).fetchall()
        return [_report_to_dict(row) for row in rows]
    finally:
        connection.close()


def get_all_reports():
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT r.*, u.full_name AS student_name, u.email AS student_email FROM reports r LEFT JOIN users u ON u.id = r.student_id ORDER BY r.created_at DESC"
        ).fetchall()
        return [_report_to_dict(row) for row in rows]
    finally:
        connection.close()


def get_report_by_id(report_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT r.*, u.full_name AS student_name, u.email AS student_email FROM reports r LEFT JOIN users u ON u.id = r.student_id WHERE r.id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
        return _report_to_dict(row)
    finally:
        connection.close()


def update_report(report_id, data):
    connection = get_connection()
    try:
        current = connection.execute(
            "SELECT * FROM reports WHERE id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
        if not current:
            return None

        fields = {
            "title": str(data.get("title", current["title"])).strip(),
            "description": str(data.get("description", current["description"])).strip(),
            "category": str(data.get("category", current["category"])).strip() or current["category"],
            "campus_location": str(data.get("campus_location", current["campus_location"])).strip(),
            "incident_date": str(data.get("incident_date", current["incident_date"] or "")).strip(),
            "incident_time": str(data.get("incident_time", current["incident_time"] or "")).strip(),
            "severity": str(data.get("severity", current["severity"])).strip() or current["severity"],
        }

        evidence_files = data.get("evidence_files")
        if evidence_files is not None:
            if isinstance(evidence_files, str):
                e_files = [evidence_files]
            elif isinstance(evidence_files, tuple):
                e_files = list(evidence_files)
            else:
                e_files = list(evidence_files)
            fields["evidence_files"] = json.dumps(e_files)
        else:
            fields["evidence_files"] = current["evidence_files"]

        columns = {row[1] for row in connection.execute("PRAGMA table_info(reports)").fetchall()}
        if "location" in columns:
            fields["location"] = fields["campus_location"]
        update_fields = {key: value for key, value in fields.items() if key in columns}
        assignments = ", ".join(f"{column} = ?" for column in update_fields)
        connection.execute(
            f"UPDATE reports SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*update_fields.values(), report_id),
        )
        connection.commit()
        updated = connection.execute(
            "SELECT r.*, u.full_name AS student_name, u.email AS student_email FROM reports r LEFT JOIN users u ON u.id = r.student_id WHERE r.id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
        return _report_to_dict(updated)
    finally:
        connection.close()


def delete_report(report_id):
    connection = get_connection()
    try:
        connection.execute("DELETE FROM responses WHERE report_id = ?", (report_id,))
        connection.execute("DELETE FROM report_status_history WHERE report_id = ?", (report_id,))
        connection.execute("DELETE FROM notifications WHERE report_id = ?", (report_id,))
        connection.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        connection.commit()
        return True
    finally:
        connection.close()


def create_response(report_id, responder_id, message):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO responses (report_id, responder_id, message) VALUES (?, ?, ?)",
            (report_id, responder_id, message.strip()),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_responses_for_report(report_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT r.*, u.full_name AS responder_name
            FROM responses r
            LEFT JOIN users u ON u.id = r.responder_id
            WHERE r.report_id = ?
            ORDER BY r.created_at ASC, r.id ASC
            """,
            (report_id,),
        ).fetchall()
        return [{
            "id": row["id"],
            "report_id": row["report_id"],
            "responder_id": row["responder_id"],
            "responder_name": row["responder_name"],
            "message": row["message"],
            "created_at": row["created_at"],
        } for row in rows]
    finally:
        connection.close()


def get_status_history(report_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT h.*, u.full_name AS changed_by_name
            FROM report_status_history h
            LEFT JOIN users u ON u.id = h.changed_by
            WHERE h.report_id = ?
            ORDER BY h.created_at ASC, h.id ASC
            """,
            (report_id,),
        ).fetchall()
        return [{
            "id": row["id"],
            "report_id": row["report_id"],
            "old_status": row["old_status"],
            "new_status": row["new_status"],
            "changed_by": row["changed_by"],
            "changed_by_name": row["changed_by_name"],
            "notes": row["notes"],
            "created_at": row["created_at"],
        } for row in rows]
    finally:
        connection.close()


def update_report_status(report_id, status, changed_by, notes=None):
    connection = get_connection()
    try:
        current = connection.execute("SELECT status FROM reports WHERE id = ? LIMIT 1", (report_id,)).fetchone()
        if not current:
            return None
        previous_status = current["status"]
        if status != previous_status:
            connection.execute(
                "INSERT INTO report_status_history (report_id, old_status, new_status, changed_by, notes) VALUES (?, ?, ?, ?, ?)",
                (report_id, previous_status, status, changed_by, notes or "")
            )
        connection.execute(
            "UPDATE reports SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, report_id),
        )
        connection.commit()
        return get_report_by_id(report_id)
    finally:
        connection.close()


def update_management_details(report_id, data, changed_by):
    connection = get_connection()
    try:
        current = connection.execute("SELECT * FROM reports WHERE id = ? LIMIT 1", (report_id,)).fetchone()
        if not current:
            return None

        new_status = str(data.get("status", current["status"])).strip() or current["status"]
        if new_status not in VALID_STATUSES:
            new_status = current["status"]

        management_response = str(data.get("management_response", current["management_response"] or "")).strip()
        action_details = str(data.get("action_details", current["action_details"] or "")).strip()
        response_changed = management_response != str(current["management_response"] or "").strip()

        if new_status != current["status"]:
            connection.execute(
                "INSERT INTO report_status_history (report_id, old_status, new_status, changed_by, notes) VALUES (?, ?, ?, ?, ?)",
                (report_id, current["status"], new_status, changed_by, management_response or action_details or "Status updated")
            )

        connection.execute(
            """
            UPDATE reports
            SET status = ?, management_response = ?, action_details = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_status, management_response, action_details, report_id),
        )
        if response_changed and management_response:
            connection.execute(
                "INSERT INTO responses (report_id, responder_id, message) VALUES (?, ?, ?)",
                (report_id, changed_by, management_response),
            )
        connection.commit()
        return get_report_by_id(report_id)
    finally:
        connection.close()


def create_notification(user_id, message, report_id=None):
    connection = get_connection()
    try:
        connection.execute(
            "INSERT INTO notifications (user_id, message, report_id) VALUES (?, ?, ?)",
            (user_id, message.strip(), report_id),
        )
        connection.commit()
        return True
    finally:
        connection.close()


def get_notification_by_id(notification_id, user_id=None):
    connection = get_connection()
    try:
        query = "SELECT * FROM notifications WHERE id = ?"
        params = [notification_id]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        row = connection.execute(query + " LIMIT 1", tuple(params)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "message": row["message"],
            "report_id": row["report_id"],
            "is_read": bool(row["is_read"]),
            "created_at": row["created_at"],
        }
    finally:
        connection.close()


def get_notifications_for_user(user_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        return [{
            "id": row["id"],
            "user_id": row["user_id"],
            "message": row["message"],
            "report_id": row["report_id"],
            "is_read": bool(row["is_read"]),
            "created_at": row["created_at"],
        } for row in rows]
    finally:
        connection.close()


def get_unread_notification_count(user_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS unread_count FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
        return int(row["unread_count"]) if row else 0
    finally:
        connection.close()


def mark_notification_read(notification_id, user_id=None):
    connection = get_connection()
    try:
        query = "UPDATE notifications SET is_read = 1 WHERE id = ?"
        params = [notification_id]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        connection.execute(query, tuple(params))
        connection.commit()
        return True
    finally:
        connection.close()


def mark_notifications_read(user_id):
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
            (user_id,),
        )
        connection.commit()
        return True
    finally:
        connection.close()
