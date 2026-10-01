"""Auto reminder for tickets nobody has commented on / acted on yet.

There's no built-in scheduler running inside this web process (a single
gunicorn worker on Render), so the actual "wake up every N minutes" part
is expected to come from an external trigger — a Render Cron Job (or any
scheduler) calling POST /cron/check-reminders on an interval, with the
CRON_SECRET header/query param. That route just calls
`check_and_send_reminders()` below.

A ticket is reminded about once when ALL of these hold:
  - reminder_enabled is True — an admin explicitly opted this ticket in
    (individually or via multi-select in the dashboard); the feature does
    NOT apply to every ticket by default
  - status is not 'closed' and not 'waiting' (waiting is excluded on
    purpose — see models.Ticket / admin blueprint)
  - not merged into another ticket, not archived
  - created_at is older than the configured threshold (hours)
  - reminder_sent is still False (reset to False whenever the ticket
    gets a new comment or its status/assignment changes — see the
    admin/public blueprints)
"""
from datetime import datetime, timedelta
from models import db, Ticket, StaffUser, ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR, get_setting
from utils.email_utils import send_ticket_unprocessed_reminder

STATUS_LABELS_AR = {'open': 'مفتوحة', 'in_progress': 'قيد المعالجة', 'waiting': 'معلقة', 'closed': 'مغلقة'}
STATUS_LABELS_EN = {'open': 'Open', 'in_progress': 'In Progress', 'waiting': 'Waiting', 'closed': 'Closed'}


def _ticket_ctx(t):
    d = t.to_dict()
    d['statusLabelAr'] = STATUS_LABELS_AR.get(t.status, t.status)
    d['statusLabelEn'] = STATUS_LABELS_EN.get(t.status, t.status)
    return d


def check_and_send_reminders():
    """Returns a small summary dict; safe to call as often as you like —
    it's a no-op unless the feature is enabled and a ticket has actually
    gone stale past the threshold."""
    if get_setting('auto_reminder_enabled', '0') != '1':
        return {'enabled': False, 'checked': 0, 'reminded': 0}

    try:
        hours = float(get_setting('auto_reminder_hours', '24') or 24)
    except (TypeError, ValueError):
        hours = 24
    hours = max(0.25, min(720, hours))
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stale = (Ticket.query
             .filter(Ticket.reminder_enabled.is_(True))
             .filter(Ticket.status.notin_(['closed', 'waiting']))
             .filter(Ticket.merged_into_id.is_(None))
             .filter(Ticket.archived.isnot(True))
             .filter(Ticket.reminder_sent.isnot(True))
             .filter(Ticket.created_at <= cutoff)
             .all())

    admin_emails = [s.email for s in StaffUser.query.filter(
        StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]), StaffUser.active.isnot(False)
    ).all() if s.email]

    reminded = 0
    for ticket in stale:
        recipients = {}
        if ticket.assignee_id and ticket.assignee and ticket.assignee.email:
            recipients[ticket.assignee.email.lower()] = ticket.assignee.full_name
        for email in admin_emails:
            recipients.setdefault(email.lower(), '')

        if not recipients:
            continue

        ctx = _ticket_ctx(ticket)
        ok_any = False
        for email, name in recipients.items():
            try:
                if send_ticket_unprocessed_reminder(ctx, round(hours), email, name):
                    ok_any = True
            except Exception as e:
                print(f"[email] reminder failed for {email}: {e}", flush=True)

        ticket.reminder_sent = True
        reminded += 1

    if stale:
        db.session.commit()

    return {'enabled': True, 'checked': len(stale), 'reminded': reminded, 'hours': hours}
