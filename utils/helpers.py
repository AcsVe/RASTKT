import re
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app


ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'pdf',
                      'doc', 'docx', 'xls', 'xlsx', 'zip', 'rar', 'txt', 'csv'}


def is_valid_email(email):
    if not email:
        return False
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email.strip()))


def sanitize_text(value):
    if not value:
        return ''
    return re.sub(r'[\x00-\x1F\x7F-\x9F\u200B-\u200D\uFEFF\u00A0]', '', str(value)).strip()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_obj):
    """Save an uploaded attachment and return its URL path."""
    if not file_obj or not allowed_file(file_obj.filename):
        return None
    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    fname = secure_filename(f'{uuid.uuid4().hex}.{ext}')
    upload_dir = current_app.config['UPLOAD_FOLDER']
    file_obj.save(os.path.join(upload_dir, fname))
    return f'/uploads/{fname}'


def db_ilike(column, value):
    """Case-insensitive exact match helper (works the same on SQLite and
    Postgres, unlike raw ilike() which SQLite doesn't support natively)."""
    from sqlalchemy import func
    return func.lower(column) == value.lower()


def match_teacher(name):
    """The core gatekeeping rule of the whole ticketing form: a ticket can
    only be created for a name that already exists — verbatim, aside from
    case/whitespace — on the teacher roster. Returns the Teacher row, or
    None if there is no match (the caller must then reject submission)."""
    from models import Teacher
    name = sanitize_text(name)
    if not name:
        return None
    return (Teacher.query
            .filter(Teacher.active.isnot(False))
            .filter(Teacher.external.isnot(True))
            .filter(db_ilike(Teacher.name, name))
            .first())
