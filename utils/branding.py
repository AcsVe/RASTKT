"""The organization's identity (names, colour, logo), editable in Settings.

Stored in app_settings (key/value) and falling back to the .env values set at setup:
  brand_org_ar / brand_org_en  — the organization name (ORG_AR / ORG_EN)
  brand_accent                 — the main colour (#RRGGBB), default appace blue
  brand_logo                   — URL of the uploaded logo; '' = the system icon (static/brand/system.svg)
"""
import os
import re
import time

from flask import current_app

SYSTEM_ICON = '/static/brand/system.svg'
SYSTEM_ICON_PNG = '/static/icon-192.png'     # e-mail clients do not show SVG
DEFAULT_ACCENT = '#0C67EC'
LOGO_EXT = {'png', 'jpg', 'jpeg', 'webp'}
_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def _setting(key, default=None):
    from models import get_setting
    try:
        return get_setting(key, default)
    except Exception:
        return default


def brand():
    cfg = current_app.config
    logo = _setting('brand_logo', None)
    if logo is None:                         # never configured (seeded at start, see seed_brand)
        logo = ''
    accent = _setting('brand_accent', '') or cfg.get('ACCENT_COLOR') or DEFAULT_ACCENT
    if not _HEX.match(accent):
        accent = DEFAULT_ACCENT
    return {
        'org_ar': _setting('brand_org_ar', '') or cfg.get('ORG_AR', ''),
        'org_en': _setting('brand_org_en', '') or cfg.get('ORG_EN', ''),
        'accent': accent,
        'logo': logo,                        # '' when the system icon is shown
        'logo_url': logo or SYSTEM_ICON,
        'icon': SYSTEM_ICON,
    }


def email_logo_url():
    """Absolute URL of the logo for e-mails (PNG system icon until a logo is uploaded)."""
    b = brand()
    logo = b['logo'] or SYSTEM_ICON_PNG
    if logo.startswith(('http://', 'https://')):
        return logo
    base = current_app.config.get('BASE_URL', '')
    return base.rstrip('/') + logo if base else ''


def seed_brand(existing_install):
    """Run once at start (models.init_db). An install that already had data keeps the logo it showed
    before this setting existed (LOGO_URL, by default the school logo in static/logo.png); a new install
    starts with the system icon until a logo is uploaded in Settings."""
    from models import get_setting, set_setting
    if get_setting('brand_logo', None) is not None:
        return
    env_logo = os.environ.get('LOGO_URL')
    if env_logo is not None:
        set_setting('brand_logo', env_logo.strip())
    else:
        set_setting('brand_logo', '/static/logo.png' if existing_install else '')


def save_logo(file_storage):
    """Store an uploaded logo under uploads/brand/ and return its URL, or None if not an image."""
    name = (file_storage.filename or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext not in LOGO_EXT:
        return None
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not (head.startswith(b'\x89PNG') or head.startswith(b'\xff\xd8') or head[8:12] == b'WEBP'):
        return None
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'brand')
    os.makedirs(folder, exist_ok=True)
    fname = f'logo-{int(time.time())}.{ext}'
    file_storage.save(os.path.join(folder, fname))
    return f'/uploads/brand/{fname}'


def valid_accent(value):
    return bool(value and _HEX.match(value))
