import re

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

def validate_email(email):
    return bool(email and EMAIL_PATTERN.match(email.strip()))

def validate_password(password):
    return bool(password) and len(password) >= 6

def validate_full_name(full_name):
    return bool(full_name) and 2 <= len(full_name.strip()) <= 100
