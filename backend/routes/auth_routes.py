from flask import Blueprint, request, jsonify, session
from backend.services.auth_service import register_student, authenticate_user
from backend.utils.validators import validate_email, validate_password, validate_full_name

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not validate_full_name(full_name):
        return jsonify(success=False, message="Please enter a valid full name."), 400
    if not validate_email(email):
        return jsonify(success=False, message="Please enter a valid email address."), 400
    if not validate_password(password):
        return jsonify(success=False, message="Password must contain at least 6 characters."), 400
    result = register_student(full_name, email, password)
    return jsonify(result), (201 if result["success"] else 409)

@auth_bp.route("/login", methods=["POST"])
def login():
    return login_user()


@auth_bp.route("/management-login", methods=["POST"])
def management_login():
    return login_user()


def login_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not email or not password:
        return jsonify(success=False, message="Email and password are required."), 400
    user = authenticate_user(email, password)
    if not user:
        return jsonify(success=False, message="Invalid email or password."), 401
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(success=True, message="Login successful.", user={
        "id": user["id"], "full_name": user["full_name"],
        "email": user["email"], "role": user["role"]
    })

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(success=True, message="Logged out successfully.")

@auth_bp.route("/profile", methods=["GET", "PATCH"])
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, message="Authentication required."), 401

    from backend.models.user_model import get_user_by_id, update_user_profile
    user = get_user_by_id(user_id)
    if not user or not user["is_active"]:
        session.clear()
        return jsonify(success=False, message="Authentication required."), 401

    if request.method == "GET":
        return jsonify(success=True, user={
            "id": user["id"], "full_name": user["full_name"],
            "email": user["email"], "role": user["role"],
            "created_at": user["created_at"], "updated_at": user["updated_at"],
        })

    data = request.get_json(silent=True) if request.is_json else None
    if not isinstance(data, dict):
        return jsonify(success=False, message="Profile update data is required."), 400

    full_name = str(data.get("full_name", user["full_name"])).strip()
    email = str(data.get("email", user["email"])).strip().lower()
    if not validate_full_name(full_name):
        return jsonify(success=False, message="Please enter a valid full name."), 400
    if not validate_email(email):
        return jsonify(success=False, message="Please enter a valid email address."), 400

    updated_user = update_user_profile(user_id, full_name=full_name, email=email)
    if not updated_user:
        return jsonify(success=False, message="An account with this email already exists."), 409

    return jsonify(success=True, message="Profile updated successfully.", user={
        "id": updated_user["id"], "full_name": updated_user["full_name"],
        "email": updated_user["email"], "role": updated_user["role"],
        "created_at": updated_user["created_at"], "updated_at": updated_user["updated_at"],
    })

@auth_bp.route("/me", methods=["GET"])
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(success=False, authenticated=False), 401
    from backend.models.user_model import get_user_by_id
    user = get_user_by_id(user_id)
    if not user or not user["is_active"]:
        session.clear()
        return jsonify(success=False, authenticated=False), 401
    return jsonify(success=True, authenticated=True, user={
        "id": user["id"], "full_name": user["full_name"],
        "email": user["email"], "role": user["role"]
    })
