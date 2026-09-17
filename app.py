import os
from flask import Flask
from models import db, init_db
from blueprints.public import public_bp
from blueprints.admin import admin_bp

def create_app():
    app = Flask(__name__)

    app.secret_key = os.environ.get('SECRET_KEY', 'acs-dev-secret-change-in-prod')

    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

    if os.path.isdir('/data'):
        db_path = '/data/acs_tickets.db'
        upload_dir = '/data/uploads'
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'acs_tickets.db')
        upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')

    os.makedirs(upload_dir, exist_ok=True)

    database_url = os.environ.get('DATABASE_URL', f'sqlite:///{db_path}')
    # requirements.txt installs psycopg (v3), not psycopg2 — SQLAlchemy's
    # default dialect for a plain postgres://... or postgresql://... URL is
    # psycopg2, which isn't installed, so force the psycopg3 dialect
    # explicitly regardless of which prefix the provider (Neon, Render, etc.)
    # handed us.
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Neon (and most managed Postgres) silently close idle connections after
    # a short timeout; pool_pre_ping tests each connection before use and
    # transparently reconnects if it's gone stale.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
    app.config['UPLOAD_FOLDER'] = upload_dir
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

    # Seeds the first Administrator account (see models.init_db).
    app.config['ADMIN_USER']    = os.environ.get('ADMIN_USER', 'admin')
    app.config['ADMIN_PASS']    = os.environ.get('ADMIN_PASS', 'acs2024')
    app.config['ORG_AR']        = os.environ.get('ORG_AR', 'مدرسة الرائد العربي')
    app.config['ORG_EN']        = os.environ.get('ORG_EN', 'Al-Raed Al-Arabi School')
    app.config['LOGO_URL']      = os.environ.get('LOGO_URL', '/static/logo.png')
    app.config['ACCENT_COLOR']  = os.environ.get('ACCENT_COLOR', '#EBB37B')
    app.config['BASE_URL']      = os.environ.get('BASE_URL', os.environ.get('RENDER_EXTERNAL_URL', '')).rstrip('/')

    # Microsoft 365 (Graph API) — sole email provider
    app.config['MS_TENANT_ID']     = os.environ.get('MS_TENANT_ID', '')
    app.config['MS_CLIENT_ID']     = os.environ.get('MS_CLIENT_ID', '')
    app.config['MS_CLIENT_SECRET'] = os.environ.get('MS_CLIENT_SECRET', '')
    app.config['MS_SENDER_EMAIL']  = os.environ.get('MS_SENDER_EMAIL', '')

    # Web Push (VAPID) — lets the server send real push notifications that
    # arrive even when a staff member's browser/PWA is fully closed. A
    # working key pair ships by default; override via env vars for your own.
    app.config['VAPID_PRIVATE_KEY'] = os.environ.get('VAPID_PRIVATE_KEY', """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg2ovCMiqrEluskjI5
qXlX0w2G814mqR4PxzhqSHHfdQWhRANCAAROV1WoRapPaAcYMgkZMIGk65s+IZpk
XEqPZq2IE3k9g455XAokrxI6N2LhLDhtu3SMlEulXPw9IcShiKeKf2xO
-----END PRIVATE KEY-----""")
    app.config['VAPID_PUBLIC_KEY'] = os.environ.get(
        'VAPID_PUBLIC_KEY', 'BE5XVahFqk9oBxgyCRkwgaTrmz4hmmRcSo9mrYgTeT2DjnlcCiSvEjo3YuEsOG27dIyUS6Vc_D0hxKGIp4p_bE4')
    app.config['VAPID_CLAIMS_EMAIL'] = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@example.com')

    # Shared secret for the external cron trigger (see /cron/check-reminders
    # below) — set this in your Render Cron Job / scheduler config as a
    # query param or X-Cron-Secret header so random visitors can't trigger it.
    app.config['CRON_SECRET'] = os.environ.get('CRON_SECRET', '')

    db.init_app(app)
    with app.app_context():
        init_db(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Served at the ROOT (not /static/sw.js) so its default scope covers the
    # whole site — a service worker's scope is limited to its own directory
    # unless served from root.
    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory, make_response
        resp = make_response(send_from_directory(app.static_folder, 'sw.js'))
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        return resp

    # Hit periodically by an external scheduler (Render Cron Job, etc.) to
    # drive the auto-reminder feature — see utils/reminder_utils.py. Not
    # gated behind the staff login (a cron job can't log in), but does
    # require CRON_SECRET so it can't be triggered by anyone else.
    @app.route('/cron/check-reminders', methods=['GET', 'POST'])
    def cron_check_reminders():
        from flask import request, jsonify
        secret = app.config.get('CRON_SECRET', '')
        provided = request.headers.get('X-Cron-Secret') or request.args.get('secret')
        if not secret or provided != secret:
            return jsonify({'error': 'forbidden'}), 403
        from utils.reminder_utils import check_and_send_reminders
        with app.app_context():
            result = check_and_send_reminders()
        return jsonify(result)

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False)
