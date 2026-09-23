"""Signed, time-limited "magic link" tokens that let a staff member act on
a ticket straight from a notification email, without first logging into
the dashboard in that browser/device.

Design notes (why it works this way):
  - The token is signed with the app's SECRET_KEY (itsdangerous), so it
    can't be forged or altered — it's the credential, scoped to exactly
    one staff account.
  - It carries WHO (staff id) and WHERE (ticket id + optional focused
    action), never the action's effect. Visiting the link only signs the
    staff member in and deep-links them into the dashboard's ticket
    detail view, already focused on that action — it never mutates the
    ticket by itself. That matters because email clients, security
    scanners and link-preview bots (e.g. Outlook Safe Links) fetch links
    automatically; a GET request must never be destructive.
  - Because it only authenticates and deep-links, permission is enforced
    exactly where it already is for the regular dashboard: the same
    StaffUser.can_manage_ticket()/can_assign() checks the ticket-row
    buttons and the API routes use. A token minted for a technical_support
    recipient simply won't show buttons/actions their role can't reach —
    nothing new to keep in sync.
  - Tokens expire (EXPIRY_SECONDS) so an old email can't be replayed
    indefinitely, but are not single-use — a staff member re-opening the
    same email later (e.g. to re-check a ticket) should still work.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app

_SALT = 'ticket-email-action-v1'
EXPIRY_SECONDS = 14 * 24 * 60 * 60  # 14 days


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt=_SALT)


def make_ticket_action_token(staff_id, ticket_id, focus=None):
    """focus: None/'' (just open the ticket), 'assign', or 'close' — must
    match a focus value templates/admin/dashboard.html's openDetail()
    already understands."""
    return _serializer().dumps({'sid': staff_id, 'tid': ticket_id, 'focus': focus or ''})


class ExpiredActionToken(Exception):
    pass


class InvalidActionToken(Exception):
    pass


def read_ticket_action_token(token):
    """Returns {'sid': int, 'tid': int, 'focus': str}. Raises
    ExpiredActionToken or InvalidActionToken."""
    try:
        return _serializer().loads(token, max_age=EXPIRY_SECONDS)
    except SignatureExpired:
        raise ExpiredActionToken()
    except BadSignature:
        raise InvalidActionToken()
