import random
import string
import secrets
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ── Roles ───────────────────────────────────────────────────────────────────
ROLE_TECH          = 'technical_support'
ROLE_SYSTEM_ADMIN  = 'system_admin'
ROLE_ADMINISTRATOR = 'administrator'
ALL_ROLES = [ROLE_TECH, ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]

ROLE_LABELS_AR = {
    ROLE_TECH: 'دعم فني',
    ROLE_SYSTEM_ADMIN: 'مسؤول نظام',
    ROLE_ADMINISTRATOR: 'مدير عام',
}
ROLE_LABELS_EN = {
    ROLE_TECH: 'Technical Support',
    ROLE_SYSTEM_ADMIN: 'System Admin',
    ROLE_ADMINISTRATOR: 'Administrator',
}

TICKET_STATUSES = ['open', 'in_progress', 'waiting', 'closed']
PRIORITIES = ['low', 'medium', 'high']


class Teacher(db.Model):
    """Roster of teachers — the only people allowed to submit a support
    ticket. A submission is rejected server-side unless it matches a row
    here (see utils.helpers.match_teacher) — unless the "accept external
    submitters" setting is on, in which case an `external=True` row is
    created on the fly for each guest and kept out of the normal roster
    views/autocomplete."""
    __tablename__ = 'teachers'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    email      = db.Column(db.String(200))
    phone      = db.Column(db.String(50))
    department = db.Column(db.String(200))   # free-text (e.g. subject/section) — informational only
    active     = db.Column(db.Boolean, default=True)
    external   = db.Column(db.Boolean, default=False)   # auto-created guest row, not a real roster entry
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email or '',
            'phone': self.phone or '', 'department': self.department or '',
            'active': self.active if self.active is not None else True,
        }


class StaffUser(db.Model):
    """A support-desk account. Three roles, each a superset of the one
    below it:
      - technical_support: comment, close/reopen, merge (own assigned tickets)
      - system_admin: all of the above on ANY ticket + assign/unassign/reassign
      - administrator: all of the above + manage staff accounts
    """
    __tablename__ = 'staff_users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name     = db.Column(db.String(200), nullable=False)
    email         = db.Column(db.String(200))
    role          = db.Column(db.String(30), nullable=False, default=ROLE_TECH)
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime)
    # Two extra-sensitive features that don't follow the normal role tiers —
    # an Administrator grants them per staff account explicitly (checkboxes
    # on the staff edit screen), independent of role. New accounts default
    # to False (off) at the Python/model level; init_db()'s migration
    # backfills True for staff who already had de-facto access before these
    # columns existed, so upgrading doesn't lock anyone out mid-use.
    can_change_priority  = db.Column(db.Boolean, default=False)
    can_manage_reminders = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id, 'username': self.username, 'fullName': self.full_name,
            'email': self.email or '', 'role': self.role,
            'roleLabelAr': ROLE_LABELS_AR.get(self.role, self.role),
            'roleLabelEn': ROLE_LABELS_EN.get(self.role, self.role),
            'active': self.active if self.active is not None else True,
            'lastLogin': self.last_login.isoformat() if self.last_login else '',
            'canChangePriority': bool(self.can_change_priority),
            'canManageReminders': bool(self.can_manage_reminders),
        }

    # ── permission helpers ──────────────────────────────────────────────
    def is_admin(self):
        return self.role == ROLE_ADMINISTRATOR

    def is_system_admin_or_above(self):
        return self.role in (ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR)

    def can_manage_ticket(self, ticket):
        """Can comment / close / reopen / archive / merge this ticket."""
        if self.is_system_admin_or_above():
            return True
        return ticket.assignee_id == self.id

    def can_assign(self):
        return self.is_system_admin_or_above()

    def can_manage_staff(self):
        return self.is_admin()

    def can_manage_categories(self):
        return self.is_system_admin_or_above()

    def can_set_priority(self):
        """Sensitive, Administrator-granted feature — independent of role
        (still requires can_manage_ticket() on the specific ticket too)."""
        return bool(self.can_change_priority)

    def can_manage_reminder_settings(self):
        """Sensitive, Administrator-granted feature — the global Auto
        Reminder for Unprocessed Tickets settings (enable/hours/check-now).
        Still requires is_system_admin_or_above() as a floor."""
        return bool(self.can_manage_reminders)


class Category(db.Model):
    """Ticket category (replaces the old booking form's "الصف / Grade"
    field) — e.g. Hardware, Software, Network, Platforms, Screens,
    Telephone System."""
    __tablename__ = 'categories'
    id         = db.Column(db.Integer, primary_key=True)
    name_ar    = db.Column(db.String(150), nullable=False)
    name_en    = db.Column(db.String(150))
    active     = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    items = db.relationship('CategoryItem', backref='category',
                             cascade='all, delete-orphan', order_by='CategoryItem.sort_order')

    def to_dict(self, with_items=False):
        d = {
            'id': self.id, 'nameAr': self.name_ar, 'nameEn': self.name_en or self.name_ar,
            'active': self.active if self.active is not None else True,
        }
        if with_items:
            d['items'] = [i.to_dict() for i in self.items]
        return d


class CategoryItem(db.Model):
    """One admin-defined identifier under a category (replaces the old
    "الحصة / Period" field) — e.g. under "Hardware": Desktop, Printer,
    Projector... each with its own identifier/code, in Arabic and/or
    English."""
    __tablename__ = 'category_items'
    id          = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    code        = db.Column(db.String(50))       # admin-assigned identifier (Arabic / default)
    code_en     = db.Column(db.String(50))       # admin-assigned identifier (English)
    name_ar     = db.Column(db.String(150), nullable=False)
    name_en     = db.Column(db.String(150))
    active      = db.Column(db.Boolean, default=True)
    sort_order  = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id, 'categoryId': self.category_id, 'code': self.code or '',
            'codeEn': self.code_en or '',
            'nameAr': self.name_ar, 'nameEn': self.name_en or self.name_ar,
            'active': self.active if self.active is not None else True,
        }


class Ticket(db.Model):
    __tablename__ = 'tickets'
    id              = db.Column(db.Integer, primary_key=True)

    # ── Numbering ─────────────────────────────────────────────────────
    # Sequential, shown to staff in the control panel. Never reused, even
    # when a ticket is merged away (its number is simply retired).
    serial_number   = db.Column(db.Integer, unique=True, nullable=False)
    # Random, given to the requester for status lookup ("للاستعلام").
    tracking_code   = db.Column(db.String(12), unique=True, nullable=False)

    # ── Requester (teacher) ──────────────────────────────────────────
    teacher_id      = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    teacher_name    = db.Column(db.String(200), nullable=False)   # snapshot
    teacher_email   = db.Column(db.String(200))
    teacher_phone   = db.Column(db.String(50))

    # ── Classification ────────────────────────────────────────────────
    category_id       = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    category_name     = db.Column(db.String(150))    # snapshot
    category_item_id  = db.Column(db.Integer, db.ForeignKey('category_items.id'))
    category_item_name = db.Column(db.String(150))   # snapshot

    subject         = db.Column(db.String(300), nullable=False)
    description     = db.Column(db.Text)
    location        = db.Column(db.String(200))     # optional free text (room / lab / office)
    priority        = db.Column(db.String(10), default='medium')   # low / medium / high
    attachments     = db.Column(db.Text)             # comma-separated URLs

    # ── Workflow ──────────────────────────────────────────────────────
    status          = db.Column(db.String(20), default='open')   # open / in_progress / waiting / closed
    assignee_id     = db.Column(db.Integer, db.ForeignKey('staff_users.id'))
    assigned_at     = db.Column(db.DateTime)

    archived        = db.Column(db.Boolean, default=False)

    # merged tickets: this ticket was folded into `merged_into_id` and its
    # own serial number is retired/cancelled.
    merged_into_id  = db.Column(db.Integer, db.ForeignKey('tickets.id'))

    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at       = db.Column(db.DateTime)
    reopened_at     = db.Column(db.DateTime)

    # ── Auto reminder (see utils.reminder_utils) ───────────────────────
    # Set once an "unprocessed ticket" reminder has been sent for the
    # current period of inactivity, so the same ticket isn't re-notified
    # every time the cron check runs. Reset to False whenever the ticket
    # gets a new comment or its status/assignment changes, so a ticket
    # that goes stale again later can trigger a fresh reminder.
    reminder_sent   = db.Column(db.Boolean, default=False)

    # Which tickets the auto-reminder sweep should even look at. Off by
    # default — an admin opts specific tickets in (individually or via
    # multi-select), rather than the feature silently applying to every
    # open ticket. The global "hours" threshold and master on/off switch
    # (AppSettings) still apply on top of this.
    reminder_enabled = db.Column(db.Boolean, default=False)

    comments = db.relationship('TicketComment', backref='ticket',
                                cascade='all, delete-orphan', order_by='TicketComment.created_at',
                                foreign_keys='TicketComment.ticket_id')

    def to_dict(self, include_internal=True):
        comments = [c.to_dict() for c in self.comments if include_internal or not c.internal]
        return {
            'id': self.id,
            'serial': self.serial_number,
            'trackingCode': self.tracking_code,
            'teacherId': self.teacher_id,
            'teacherName': self.teacher_name,
            'teacherEmail': self.teacher_email or '',
            'teacherPhone': self.teacher_phone or '',
            'categoryId': self.category_id,
            'category': self.category_name or '',
            'categoryItemId': self.category_item_id,
            'categoryItem': self.category_item_name or '',
            'subject': self.subject,
            'description': self.description or '',
            'location': self.location or '',
            'priority': self.priority or 'medium',
            'attachments': [a for a in (self.attachments or '').split(',') if a],
            'status': self.status,
            'assigneeId': self.assignee_id,
            'assigneeName': self.assignee.full_name if self.assignee_id and self.assignee else '',
            'assignedAt': self.assigned_at.isoformat() if self.assigned_at else '',
            'archived': self.archived or False,
            'mergedIntoId': self.merged_into_id,
            'mergedIntoSerial': self.merged_into.serial_number if self.merged_into_id and self.merged_into else None,
            'createdAt': self.created_at.isoformat() if self.created_at else '',
            'closedAt': self.closed_at.isoformat() if self.closed_at else '',
            'reopenedAt': self.reopened_at.isoformat() if self.reopened_at else '',
            'reminderEnabled': self.reminder_enabled or False,
            'comments': comments,
        }

    def to_monitor_dict(self):
        """Reduced, privacy-conscious view used by the public, no-login
        Monitoring page: no requester contact info (email/phone) and no
        internal-only comments."""
        return {
            'id': self.id,  # needed so the frontend can look up the exact
                             # ticket that was clicked (not just the first
                             # one in whatever list is currently loaded)
            'serial': self.serial_number,
            'teacherName': self.teacher_name,
            'category': self.category_name or '',
            'categoryItem': self.category_item_name or '',
            'subject': self.subject,
            'priority': self.priority or 'medium',
            'status': self.status,
            'assigneeName': self.assignee.full_name if self.assignee_id and self.assignee else '',
            'createdAt': self.created_at.isoformat() if self.created_at else '',
            'closedAt': self.closed_at.isoformat() if self.closed_at else '',
            'archived': self.archived or False,
        }


Ticket.assignee = db.relationship('StaffUser', foreign_keys=[Ticket.assignee_id])
Ticket.merged_into = db.relationship('Ticket', remote_side=[Ticket.id], foreign_keys=[Ticket.merged_into_id])


class TicketComment(db.Model):
    """One entry in a ticket's shared communication log. Either side —
    the requester (teacher) or a staff member — can post one; `internal`
    marks a staff-only note that never shows on the requester's lookup
    page."""
    __tablename__ = 'ticket_comments'
    id          = db.Column(db.Integer, primary_key=True)
    ticket_id   = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    author_role = db.Column(db.String(20), nullable=False)   # 'teacher' | 'staff' | 'system'
    author_name = db.Column(db.String(200))
    staff_id    = db.Column(db.Integer, db.ForeignKey('staff_users.id'))
    body        = db.Column(db.Text, nullable=False)
    internal    = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'ticketId': self.ticket_id, 'authorRole': self.author_role,
            'authorName': self.author_name or '', 'body': self.body,
            'internal': self.internal or False,
            'createdAt': self.created_at.isoformat() if self.created_at else '',
        }


class PushSubscription(db.Model):
    """A staff device's Web Push subscription (collected from the
    installed admin PWA) so the server can notify staff of new/assigned
    tickets even when their browser is fully closed."""
    __tablename__ = 'push_subscriptions'
    id         = db.Column(db.Integer, primary_key=True)
    staff_id   = db.Column(db.Integer, db.ForeignKey('staff_users.id'))
    endpoint   = db.Column(db.Text, nullable=False, unique=True)
    p256dh     = db.Column(db.String(255), nullable=False)
    auth       = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_push_dict(self):
        return {'endpoint': self.endpoint, 'keys': {'p256dh': self.p256dh, 'auth': self.auth}}


class AppSetting(db.Model):
    """Simple key/value store for system-wide toggles (e.g. whether to
    accept tickets from people outside the teacher roster)."""
    __tablename__ = 'app_settings'
    key   = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)


def get_setting(key, default=None):
    row = AppSetting.query.get(key)
    return row.value if row is not None else default


def set_setting(key, value):
    row = AppSetting.query.get(key)
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = value
    db.session.commit()


def gen_serial_number():
    """Next sequential ticket number. Retries on unique-constraint races
    (single gunicorn worker in this app's deployment makes that
    vanishingly rare, but this keeps it correct either way)."""
    last = db.session.query(db.func.max(Ticket.serial_number)).scalar()
    return (last or 0) + 1


def gen_tracking_code():
    """Short random code the requester uses to look their ticket up.
    Avoids visually-ambiguous characters (0/O, 1/I)."""
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(7))
        if not Ticket.query.filter_by(tracking_code=code).first():
            return code


def init_db(app):
    """Create tables and seed default categories + the first Administrator
    account if the database is empty."""
    db.create_all()

    # Lightweight in-place migration for older/partial databases.
    try:
        with db.engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE teachers ADD COLUMN IF NOT EXISTS department VARCHAR(200)")
            conn.exec_driver_sql("ALTER TABLE teachers ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE")
            conn.exec_driver_sql("ALTER TABLE teachers ADD COLUMN IF NOT EXISTS external BOOLEAN DEFAULT FALSE")
            conn.exec_driver_sql("ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS staff_id INTEGER")
            conn.exec_driver_sql("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS priority VARCHAR(10) DEFAULT 'medium'")
            conn.exec_driver_sql("ALTER TABLE category_items ADD COLUMN IF NOT EXISTS code_en VARCHAR(50)")
            conn.exec_driver_sql("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT FALSE")
            conn.exec_driver_sql("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT FALSE")
            # No DEFAULT here on purpose — existing rows land NULL so the
            # one-time backfill right below can tell "never set" apart from
            # an Administrator later explicitly switching it back off.
            conn.exec_driver_sql("ALTER TABLE staff_users ADD COLUMN IF NOT EXISTS can_change_priority BOOLEAN")
            conn.exec_driver_sql("ALTER TABLE staff_users ADD COLUMN IF NOT EXISTS can_manage_reminders BOOLEAN")
            conn.commit()
    except Exception:
        pass

    # One-time backfill for the two sensitive per-staff permissions above:
    # staff who already had de-facto access via their role before these
    # columns existed keep working after the upgrade; every other still-NULL
    # row (including anyone created fresh after this point) settles to
    # False. Runs every startup but is a no-op once every row has a real
    # value — an Administrator's later explicit change is never NULL again,
    # so it's never touched here.
    try:
        StaffUser.query.filter(
            StaffUser.can_change_priority.is_(None), StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]),
        ).update({'can_change_priority': True}, synchronize_session=False)
        StaffUser.query.filter(StaffUser.can_change_priority.is_(None)).update(
            {'can_change_priority': False}, synchronize_session=False)
        StaffUser.query.filter(
            StaffUser.can_manage_reminders.is_(None), StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]),
        ).update({'can_manage_reminders': True}, synchronize_session=False)
        StaffUser.query.filter(StaffUser.can_manage_reminders.is_(None)).update(
            {'can_manage_reminders': False}, synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()

    import os
    if StaffUser.query.count() == 0:
        from werkzeug.security import generate_password_hash
        username = os.environ.get('ADMIN_USER', 'admin')
        password = os.environ.get('ADMIN_PASS', 'acs2024')
        db.session.add(StaffUser(
            username=username,
            password_hash=generate_password_hash(password),
            full_name='Administrator',
            role=ROLE_ADMINISTRATOR,
            active=True,
            # The very first (seed) account — give it both sensitive
            # permissions immediately, or a brand-new install would leave
            # even the sole Administrator unable to touch Priority or the
            # reminder settings until... an Administrator enables them.
            can_change_priority=True,
            can_manage_reminders=True,
        ))
        db.session.commit()

    if Category.query.count() == 0:
        defaults = [
            ('الأجهزة', 'Hardware'),
            ('البرمجيات', 'Software'),
            ('الشبكة', 'Network'),
            ('المنصات التعليمية', 'Platforms'),
            ('الشاشات', 'Screens'),
            ('نظام الهاتف', 'Telephone System'),
        ]
        for i, (ar, en) in enumerate(defaults):
            db.session.add(Category(name_ar=ar, name_en=en, active=True, sort_order=i))
        db.session.commit()
