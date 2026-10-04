import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
IS_PRODUCTION = os.environ.get("APP_ENV", "").lower() == "production" or os.environ.get("RENDER", "").lower() == "true"

_default_database_path = os.path.join(BASE_DIR, "database", "campus_safety.db")
DATABASE_PATH = os.path.abspath(os.environ.get("DATABASE_PATH", _default_database_path))
DATABASE_DIR = os.path.dirname(DATABASE_PATH)
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")

SECRET_KEY = os.environ.get("SECRET_KEY")
if IS_PRODUCTION and not SECRET_KEY:
	raise RuntimeError("SECRET_KEY must be set in production.")
SECRET_KEY = SECRET_KEY or "campus-safety-logger-local-development-only"

DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not IS_PRODUCTION:
	DEFAULT_ADMIN_EMAIL = DEFAULT_ADMIN_EMAIL or "admin@123"
	DEFAULT_ADMIN_PASSWORD = DEFAULT_ADMIN_PASSWORD or "admin"

UPLOAD_FOLDER = os.path.abspath(os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads", "evidence")))
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024))
