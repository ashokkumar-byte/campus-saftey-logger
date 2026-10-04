import os
import uuid
from datetime import date, datetime, time
from flask import Blueprint, jsonify, request, session
from flask import send_from_directory
from werkzeug.utils import secure_filename

from backend.models.report_model import (
    VALID_STATUSES,
    create_notification,
    create_report,
    create_response,
    delete_report,
    get_all_reports,
    get_notification_by_id,
    get_notifications_for_user,
    get_report_by_id,
    get_reports_for_user,
    get_responses_for_report,
    get_status_history,
    get_unread_notification_count,
    mark_notification_read,
    mark_notifications_read,
    update_management_details,
    update_report,
)
from backend.models.user_model import get_user_by_id
from config import ALLOWED_IMAGE_EXTENSIONS, UPLOAD_FOLDER

report_bp = Blueprint("reports", __name__, url_prefix="/api")
UNSUPPORTED_REPORT_FIELDS = {"assigned_department", "assigned_staff", "investigation_notes"}


def require_auth():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_user_by_id(user_id)
    if not user or not user["is_active"]:
        session.clear()
        return None
    return user


def get_management_users():
    from backend.models.user_model import get_connection

    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT id FROM users WHERE role = 'management' AND is_active = 1"
        ).fetchall()
        return [row["id"] for row in rows]
    finally:
        connection.close()


def is_allowed_upload(filename):
    if not filename:
        return False
    extension = os.path.splitext(filename)[1].lower().lstrip(".")
    return extension in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_evidence():
    uploads = [item for item in request.files.getlist("evidence") if item and item.filename]
    for uploaded_file in uploads:
        safe_name = secure_filename(uploaded_file.filename)
        if not is_allowed_upload(safe_name):
            return None, "Evidence must be a PNG, JPG, JPEG, or WEBP image."

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filenames = []
    try:
        for uploaded_file in uploads:
            extension = os.path.splitext(secure_filename(uploaded_file.filename))[1].lower()
            name = f"{uuid.uuid4().hex}{extension}"
            uploaded_file.save(os.path.join(UPLOAD_FOLDER, name))
            filenames.append(name)
    except Exception:
        for filename in filenames:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, filename))
            except OSError:
                pass
        raise
    return filenames, None


def parse_payload():
    payload = request.get_json(silent=True)
    if payload is not None:
        return payload if isinstance(payload, dict) else {}
    return request.form.to_dict()


def normalize_report_payload(payload):
    values = dict(payload)
    if not values.get("campus_location") and values.get("location"):
        values["campus_location"] = values["location"]

    incident_datetime = values.pop("incident_datetime", "")
    if incident_datetime:
        try:
            parsed_datetime = datetime.fromisoformat(str(incident_datetime))
        except ValueError:
            return values, "Please enter a valid incident date and time."
        values["incident_date"] = parsed_datetime.date().isoformat()
        values["incident_time"] = parsed_datetime.time().strftime("%H:%M")

    return values, None


def validate_report_contract(payload):
    unsupported = UNSUPPORTED_REPORT_FIELDS.intersection(payload)
    if unsupported:
        return "Assignment and investigation fields are not supported."
    if "evidence_files" in payload:
        return "Evidence must be uploaded with the report."
    return None


def validate_report_payload(payload, existing=None):
    values = {**(existing or {}), **payload}
    required_fields = {
        "description": "Description",
        "category": "Category",
        "campus_location": "Location",
        "incident_date": "Date",
        "incident_time": "Time",
        "severity": "Severity",
    }
    missing = [label for field, label in required_fields.items() if not str(values.get(field, "")).strip()]
    if missing:
        return f"Please complete these required fields: {', '.join(missing)}."

    limits = {
        "title": 150,
        "description": 5000,
        "incident_type": 120,
        "campus_location": 120,
        "building_area": 120,
        "people_involved": 200,
        "witnesses": 200,
        "additional_details": 5000,
    }
    for field, maximum in limits.items():
        if len(str(values.get(field, ""))) > maximum:
            return f"{field.replace('_', ' ').capitalize()} must be {maximum} characters or fewer."

    options = {
        "category": {"Safety", "Facilities", "Medical", "Harassment", "Security"},
        "severity": {"Critical", "High", "Medium", "Low"},
        "urgency": {"Immediate", "High", "Normal", "Low"},
        "contact_preference": {"Email", "Phone", "Text"},
    }
    for field, allowed in options.items():
        if values.get(field) and values[field] not in allowed:
            return f"Please choose a valid {field.replace('_', ' ')}."

    try:
        date.fromisoformat(str(values["incident_date"]))
    except ValueError:
        return "Please enter a valid incident date."
    try:
        time.fromisoformat(str(values["incident_time"]))
    except ValueError:
        return "Please enter a valid incident time."

    for field in ("immediate_danger", "injury_involved", "emergency_assistance_required"):
        value = values.get(field, False)
        if isinstance(value, str) and value.strip().lower() not in {"yes", "no", "true", "false", "1", "0"}:
            return f"Please choose Yes or No for {field.replace('_', ' ')}."
        if isinstance(value, int) and not isinstance(value, bool) and value not in {0, 1}:
            return f"Please choose Yes or No for {field.replace('_', ' ')}."
        if not isinstance(value, (str, bool, int)):
            return f"Please choose Yes or No for {field.replace('_', ' ')}."

    return None


@report_bp.route("/reports", methods=["GET", "POST"])
def reports():
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    if request.method == "GET":
        reports = get_all_reports() if user["role"] == "management" else get_reports_for_user(user["id"])
        return jsonify(success=True, reports=reports), 200

    if user["role"] == "management":
        return jsonify(success=False, message="Management accounts cannot submit student safety reports."), 403

    payload, normalization_error = normalize_report_payload(parse_payload())
    if normalization_error:
        return jsonify(success=False, message=normalization_error), 400
    contract_error = validate_report_contract(payload)
    if contract_error:
        return jsonify(success=False, message=contract_error), 400
    validation_error = validate_report_payload(payload)
    if validation_error:
        return jsonify(success=False, message=validation_error), 400

    files, upload_error = save_uploaded_evidence()
    if upload_error:
        return jsonify(success=False, message=upload_error), 400
    payload["evidence_files"] = files
    try:
        report = create_report(payload, user["id"])
    except Exception:
        for filename in files:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, filename))
            except OSError:
                pass
        raise
    for management_id in get_management_users():
        create_notification(management_id, f"New safety report {report['report_id']} submitted.", report["id"])

    return jsonify(success=True, message="Safety report submitted successfully.", report=report), 201


@report_bp.route("/reports/<int:report_id>", methods=["GET", "PATCH", "DELETE"])
def report_detail(report_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404

    if user["role"] != "management" and report["student_id"] != user["id"]:
        return jsonify(success=False, message="You do not have permission to access this report."), 403

    if request.method in {"PATCH", "DELETE"}:
        if user["role"] == "management":
            return jsonify(success=False, message="Management cannot edit or delete student reports."), 403
        if report["status"] != "Submitted":
            return jsonify(success=False, message="Only submitted reports can be edited or deleted."), 409

    if request.method == "GET":
        return jsonify(success=True, report=report, status_history=get_status_history(report_id), responses=get_responses_for_report(report_id)), 200

    if request.method == "DELETE":
        delete_report(report_id)
        return jsonify(success=True, message="Report deleted successfully."), 200

    payload, normalization_error = normalize_report_payload(parse_payload())
    if normalization_error:
        return jsonify(success=False, message=normalization_error), 400
    contract_error = validate_report_contract(payload)
    if contract_error:
        return jsonify(success=False, message=contract_error), 400
    if not payload:
        return jsonify(success=False, message="No report data provided."), 400

    validation_error = validate_report_payload(payload, report)
    if validation_error:
        return jsonify(success=False, message=validation_error), 400

    files, upload_error = save_uploaded_evidence()
    if upload_error:
        return jsonify(success=False, message=upload_error), 400
    if files:
        payload["evidence_files"] = [*report["evidence_files"], *files]
    try:
        updated = update_report(report_id, payload)
    except Exception:
        for filename in files:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, filename))
            except OSError:
                pass
        raise
    if not updated:
        for filename in files:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, filename))
            except OSError:
                pass
        return jsonify(success=False, message="Report not found."), 404
    return jsonify(success=True, message="Report updated successfully.", report=updated), 200


@report_bp.route("/reports/<int:report_id>/management", methods=["POST"])
def report_management_update(report_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401
    if user["role"] != "management":
        return jsonify(success=False, message="Only management can update reports."), 403

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404

    payload = parse_payload()
    contract_error = validate_report_contract(payload)
    if contract_error:
        return jsonify(success=False, message=contract_error), 400
    status = str(payload.get("status", report["status"])).strip()
    if status and status not in VALID_STATUSES:
        return jsonify(success=False, message="Invalid status selected."), 400

    updated = update_management_details(report_id, payload, user["id"])
    response_message = str(payload.get("management_response", "")).strip()
    if response_message and response_message != str(report.get("management_response") or "").strip():
        create_notification(report["student_id"], f"Management update for {report['report_id']}: {response_message}", report_id)

    if updated["status"] != report["status"]:
        create_notification(report["student_id"], f"Report {report['report_id']} status changed to {updated['status']}.", report_id)
    return jsonify(success=True, message="Report updated successfully.", report=updated), 200


@report_bp.route("/reports/<int:report_id>/status", methods=["PATCH"])
def report_status_update(report_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401
    if user["role"] != "management":
        return jsonify(success=False, message="Only management can update report status."), 403

    payload = parse_payload()
    status = str(payload.get("status", "")).strip()
    if not status or status not in VALID_STATUSES:
        return jsonify(success=False, message="A valid status is required."), 400

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404

    updated = update_management_details(report_id, {"status": status}, user["id"])
    if updated["status"] != report["status"]:
        create_notification(report["student_id"], f"Report {report['report_id']} status changed to {status}.", report_id)
    return jsonify(success=True, message="Report status updated successfully.", report=updated), 200


@report_bp.route("/reports/<int:report_id>/responses", methods=["GET", "POST"])
def report_responses(report_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404

    if user["role"] != "management" and report["student_id"] != user["id"]:
        return jsonify(success=False, message="You do not have permission to access responses for this report."), 403

    if request.method == "GET":
        return jsonify(success=True, responses=get_responses_for_report(report_id)), 200

    if user["role"] != "management":
        return jsonify(success=False, message="Only management can add responses."), 403

    payload = parse_payload()
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify(success=False, message="Response message is required."), 400

    response_id = create_response(report_id, user["id"], message)
    create_notification(report["student_id"], f"Management response for {report['report_id']}: {message}", report_id)
    return jsonify(success=True, message="Response added successfully.", response_id=response_id), 201


@report_bp.route("/reports/<int:report_id>/history", methods=["GET"])
def report_history(report_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404

    if user["role"] != "management" and report["student_id"] != user["id"]:
        return jsonify(success=False, message="You do not have permission to access this report history."), 403

    return jsonify(success=True, history=get_status_history(report_id)), 200


@report_bp.route("/reports/<int:report_id>/evidence/<path:filename>", methods=["GET"])
def report_evidence(report_id, filename):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    report = get_report_by_id(report_id)
    if not report:
        return jsonify(success=False, message="Report not found."), 404
    if user["role"] != "management" and report["student_id"] != user["id"]:
        return jsonify(success=False, message="You do not have permission to access this evidence."), 403
    if secure_filename(filename) != filename or filename not in report["evidence_files"]:
        return jsonify(success=False, message="Evidence file not found."), 404

    evidence_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.isfile(evidence_path):
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)

    legacy_upload_folder = os.path.dirname(UPLOAD_FOLDER)
    if os.path.isfile(os.path.join(legacy_upload_folder, filename)):
        return send_from_directory(legacy_upload_folder, filename, as_attachment=False)
    return jsonify(success=False, message="Evidence file not found."), 404


@report_bp.route("/notifications", methods=["GET", "POST"])
def notifications():
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    if request.method == "POST":
        mark_notifications_read(user["id"])
        return jsonify(success=True, message="Notifications marked as read."), 200

    return jsonify(
        success=True,
        notifications=get_notifications_for_user(user["id"]),
        unread_count=get_unread_notification_count(user["id"]),
    ), 200


@report_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
def notification_detail(notification_id):
    user = require_auth()
    if not user:
        return jsonify(success=False, message="Authentication required."), 401

    notification = get_notification_by_id(notification_id, user["id"])
    if not notification:
        return jsonify(success=False, message="Notification not found."), 404

    mark_notification_read(notification_id, user["id"])
    notification["is_read"] = True
    return jsonify(success=True, message="Notification marked as read.", notification=notification), 200
