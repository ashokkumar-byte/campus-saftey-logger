import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "campus_safety.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "campus-safety-logger-development-key")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "evidence")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
