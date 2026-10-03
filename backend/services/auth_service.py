import sqlite3

from backend.models.user_model import create_user, get_user_by_email
from backend.utils.security import hash_password, verify_password

def register_student(full_name, email, password):
    if get_user_by_email(email):
        return {"success": False, "message": "An account with this email already exists."}
    try:
        user_id = create_user(full_name, email, hash_password(password), "student")
    except sqlite3.IntegrityError:
        return {"success": False, "message": "An account with this email already exists."}
    return {"success": True, "message": "Registration successful", "user_id": user_id}

def authenticate_user(email, password):
    user = get_user_by_email(email)
    if not user or not user["is_active"]:
        return None
    if not verify_password(user["password_hash"], password):
        return None
    return user
