"""The staff mobile app (/admin/m/): a single-page help-desk client in the style of the leading help-desk apps
(ticket views with counts, conversation thread, reply / internal note, quick status, priority and assignment),
opened by the Android admin app (android-admin/) and usable in any phone browser.

It uses the same session and the same permission rules as the admin panel: the ticket actions themselves go to
the existing /admin/api/tickets/<id>/... endpoints. This module adds only what a phone needs on top: a JSON sign-in,
a light ticket list with the counts of every view, the ticket with the actions the signed-in staff may take, and a
small «what is new since …» feed for notifications.
"""
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash

from models import (ROLE_TECH, StaffUser, Ticket, TicketComment, db)
from utils.helpers import db_ilike, sanitize_text

mobile_bp = Blueprint('mobile', __name__)

VIEWS = ('mine', 'unassigned', 'open', 'in_progress', 'waiting', 'closed', 'all')
_FAILED = {}


def _staff():
    sid = session.get('staff_id')
    s = StaffUser.query.get(sid) if sid else None
    return s if s and s.active else None


def _me(s):
    d = s.to_dict()
    d.update({'canAssign': s.can_assign(), 'canPriority': s.can_set_priority(),
              'isTech': s.role == ROLE_TECH, 'lang': session.get('admin_lang', 'ar')})
    return d


@mobile_bp.after_request
def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@mobile_bp.route('/')
def app_shell():
    import os
    from flask import current_app
    v = 0
    for f in ('app.js', 'app.css'):
        try:
            v = max(v, int(os.path.getmtime(os.path.join(current_app.static_folder, 'm', f))))
        except OSError:
            pass
    return render_template('admin/mobile.html', lang=session.get('admin_lang', 'ar'), v=v)


@mobile_bp.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json(silent=True) or {}
    ip = request.headers.get('CF-Connecting-IP') or request.remote_addr or ''
    n, first = _FAILED.get(ip, (0, datetime.utcnow()))
    if n >= 10 and (datetime.utcnow() - first).total_seconds() < 900:
        return jsonify({'error': 'too_many'}), 429
    u = sanitize_text(d.get('username', ''))
    staff = StaffUser.query.filter(db_ilike(StaffUser.username, u)).first() if u else None
    if not staff or not staff.active or not check_password_hash(staff.password_hash, d.get('password', '')):
        _FAILED[ip] = (n + 1, first)
        return jsonify({'error': 'invalid'}), 401
    _FAILED.pop(ip, None)
    session.permanent = True
    session['staff_id'] = staff.id
    session['admin_lang'] = 'en' if d.get('lang') == 'en' else 'ar'
    staff.last_login = datetime.utcnow()
    db.session.commit()
    return jsonify(_me(staff))


@mobile_bp.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('staff_id', None)
    return jsonify({'ok': True})


@mobile_bp.route('/api/me')
def api_me():
    s = _staff()
    if not s:
        return jsonify({'error': 'auth'}), 401
    return jsonify(_me(s))


@mobile_bp.route('/api/lang', methods=['POST'])
def api_lang():
    if not _staff():
        return jsonify({'error': 'auth'}), 401
    session['admin_lang'] = 'en' if (request.get_json(silent=True) or {}).get('lang') == 'en' else 'ar'
    return jsonify({'ok': True})


def _base_query(s):
    q = (Ticket.query.filter(Ticket.archived.isnot(True), Ticket.merged_into_id.is_(None))
         .options(selectinload(Ticket.comments)))
    if s.role == ROLE_TECH:                       # technical support works on its own queue only
        q = q.filter(Ticket.assignee_id == s.id)
    return q


def _in_view(t, view, me_id):
    if view == 'mine':
        return t.assignee_id == me_id and t.status != 'closed'
    if view == 'unassigned':
        return t.assignee_id is None and t.status != 'closed'
    if view in ('open', 'in_progress', 'waiting', 'closed'):
        return t.status == view
    return True


def _lite(t):
    visible = [c for c in t.comments if c.author_role != 'system']
    last = visible[-1] if visible else None
    activity = max([t.created_at] + [c.created_at for c in t.comments if c.created_at]) if t.created_at else None
    return {
        'id': t.id, 'serial': t.serial_number, 'subject': t.subject, 'teacherName': t.teacher_name,
        'category': t.category_name or '', 'categoryItem': t.category_item_name or '', 'location': t.location or '',
        'priority': t.priority or 'medium', 'status': t.status, 'assigneeId': t.assignee_id,
        'assigneeName': t.assignee.full_name if t.assignee_id and t.assignee else '',
        'createdAt': t.created_at.isoformat() if t.created_at else '',
        'activityAt': activity.isoformat() if activity else '',
        'replies': len(visible),
        'last': ({'author': last.author_name or '', 'role': last.author_role, 'internal': bool(last.internal),
                  'body': (last.body or '')[:140]} if last else None),
        'attachments': len([a for a in (t.attachments or '').split(',') if a]),
    }


@mobile_bp.route('/api/tickets')
def api_tickets():
    s = _staff()
    if not s:
        return jsonify({'error': 'auth'}), 401
    view = request.args.get('view', 'mine' if s.role == ROLE_TECH else 'unassigned')
    view = view if view in VIEWS else 'all'
    q = _base_query(s)
    search = (request.args.get('q') or '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Ticket.subject.ilike(like), Ticket.teacher_name.ilike(like),
                            Ticket.tracking_code.ilike(like), Ticket.location.ilike(like),
                            db.cast(Ticket.serial_number, db.String).ilike(like)))
    tickets = q.all()
    counts = {v: sum(1 for t in tickets if _in_view(t, v, s.id)) for v in VIEWS}
    rows = [_lite(t) for t in tickets if _in_view(t, view, s.id)]
    order = {'high': 0, 'medium': 1, 'low': 2}
    if view == 'closed':
        rows.sort(key=lambda r: r['activityAt'], reverse=True)
    else:                                         # high priority first, then the most recent activity
        rows.sort(key=lambda r: r['activityAt'], reverse=True)
        rows.sort(key=lambda r: order.get(r['priority'], 1))
    return jsonify({'view': view, 'counts': counts, 'tickets': rows, 'now': datetime.utcnow().isoformat()})


@mobile_bp.route('/api/tickets/<int:ticket_id>')
def api_ticket(ticket_id):
    s = _staff()
    if not s:
        return jsonify({'error': 'auth'}), 401
    t = Ticket.query.get_or_404(ticket_id)
    if s.role == ROLE_TECH and t.assignee_id != s.id:
        return jsonify({'error': 'not_found'}), 404
    d = t.to_dict()
    manage = s.can_manage_ticket(t)
    d['can'] = {'manage': manage, 'assign': s.can_assign(), 'priority': manage and s.can_set_priority()}
    if s.can_assign():
        d['staff'] = [{'id': x.id, 'name': x.full_name, 'role': x.role}
                      for x in StaffUser.query.filter(StaffUser.active.isnot(False)).order_by(StaffUser.full_name)]
    return jsonify(d)


@mobile_bp.route('/api/updates')
def api_updates():
    """New tickets, assignments and replies since ``since`` (UTC ISO) that concern the signed-in staff —
    the app turns them into notifications."""
    s = _staff()
    if not s:
        return jsonify({'error': 'auth'}), 401
    now = datetime.utcnow()
    try:
        since = datetime.fromisoformat((request.args.get('since') or '')[:26])
    except ValueError:
        return jsonify({'events': [], 'now': now.isoformat()})
    events = []
    base = Ticket.query.filter(Ticket.merged_into_id.is_(None))
    if s.role != ROLE_TECH:
        for t in base.filter(Ticket.created_at > since).all():
            events.append({'kind': 'new', 'ticketId': t.id, 'serial': t.serial_number, 'subject': t.subject,
                           'who': t.teacher_name, 'at': t.created_at.isoformat()})
    for t in base.filter(Ticket.assignee_id == s.id, Ticket.assigned_at > since).all():
        events.append({'kind': 'assigned', 'ticketId': t.id, 'serial': t.serial_number, 'subject': t.subject,
                       'who': '', 'at': t.assigned_at.isoformat()})
    cq = (TicketComment.query.join(Ticket, Ticket.id == TicketComment.ticket_id)
          .filter(TicketComment.created_at > since, TicketComment.author_role != 'system',
                  db.or_(TicketComment.staff_id.is_(None), TicketComment.staff_id != s.id)))
    if s.role == ROLE_TECH:
        cq = cq.filter(Ticket.assignee_id == s.id)
    for c in cq.order_by(TicketComment.created_at).limit(30).all():
        t = c.ticket
        events.append({'kind': 'note' if c.internal else 'reply', 'ticketId': t.id, 'serial': t.serial_number,
                       'subject': t.subject, 'who': c.author_name or t.teacher_name, 'body': (c.body or '')[:120],
                       'at': c.created_at.isoformat()})
    events.sort(key=lambda e: e['at'])
    return jsonify({'events': events[-30:], 'now': now.isoformat()})


@mobile_bp.route('/api/activity')
def api_activity():
    """The latest replies and notes on the tickets the staff can see (the app's «النشاط» tab)."""
    s = _staff()
    if not s:
        return jsonify({'error': 'auth'}), 401
    cq = (TicketComment.query.join(Ticket, Ticket.id == TicketComment.ticket_id)
          .filter(TicketComment.author_role != 'system', Ticket.merged_into_id.is_(None)))
    if s.role == ROLE_TECH:
        cq = cq.filter(Ticket.assignee_id == s.id)
    out = []
    for c in cq.order_by(TicketComment.created_at.desc()).limit(60).all():
        t = c.ticket
        out.append({'ticketId': t.id, 'serial': t.serial_number, 'subject': t.subject, 'status': t.status,
                    'who': c.author_name or t.teacher_name, 'role': c.author_role, 'internal': bool(c.internal),
                    'body': (c.body or '')[:160], 'at': c.created_at.isoformat() if c.created_at else ''})
    return jsonify(out)
