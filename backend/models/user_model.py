import sqlite3
from config import DATABASE_PATH

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def get_user_by_email(email):
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT * FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1",
            (email.strip(),)
        ).fetchone()
    finally:
        connection.close()

def get_user_by_id(user_id):
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT * FROM users WHERE id=? LIMIT 1",
            (user_id,)
        ).fetchone()
    finally:
        connection.close()

def create_user(full_name, email, password_hash, role="student"):
    connection = get_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO users (full_name,email,password_hash,role) VALUES (?,?,?,?)",
            (full_name.strip(), email.strip().lower(), password_hash, role)
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def update_user_profile(user_id, full_name=None, email=None):
    connection = get_connection()
    try:
        current = connection.execute(
            "SELECT * FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if not current:
            return None

        updated_full_name = (full_name or current["full_name"]).strip()
        updated_email = (email or current["email"]).strip().lower()
        if not updated_full_name:
            return None

        cursor = connection.execute(
            "UPDATE users SET full_name = ?, email = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (updated_full_name, updated_email, user_id),
        )
        connection.commit()
        return connection.execute(
            "SELECT * FROM users WHERE id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        connection.close()
