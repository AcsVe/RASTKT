from datetime import datetime, timedelta
import re
from collections import defaultdict
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (Blueprint, render_template, request, jsonify,
                    session, redirect, url_for, current_app)
from models import (db, Ticket, TicketComment, Teacher, Category, CategoryItem,
                     StaffUser, PushSubscription,
                     ROLE_TECH, ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR, ALL_ROLES,
                     ROLE_LABELS_AR, ROLE_LABELS_EN, PRIORITIES, get_setting, set_setting)
from utils.helpers import is_valid_email, sanitize_text, db_ilike
from utils.email_utils import (send_ticket_assigned, send_ticket_closed, send_ticket_reopened,
                                send_ticket_merged, send_new_comment_notification, send_priority_changed,
                                send_internal_note_notification, send_new_staff_account_email,
                                send_ticket_reassigned_away)
from utils.action_tokens import read_ticket_action_token, ExpiredActionToken, InvalidActionToken

admin_bp = Blueprint('admin', __name__)


@admin_bp.after_request
def _no_cache(resp):
    # The whole admin panel is session-gated and its pages change often
    # (ticket lists, staff, etc.) — never let the browser's disk cache or
    # back/forward cache (bfcache) serve a stale copy. This is also what
    # makes the phone's back button reliably re-check the session instead
    # of occasionally flashing an old cached screen.
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

STATUS_LABELS_AR = {'open': 'مفتوحة', 'in_progress': 'قيد المعالجة', 'waiting': 'معلقة', 'closed': 'مغلقة'}
STATUS_LABELS_EN = {'open': 'Open', 'in_progress': 'In Progress', 'waiting': 'Waiting', 'closed': 'Closed'}


def _ticket_email_ctx(t, **extra):
    d = t.to_dict()
    d['statusLabelAr'] = STATUS_LABELS_AR.get(t.status, t.status)
    d['statusLabelEn'] = STATUS_LABELS_EN.get(t.status, t.status)
    if t.assignee_id and t.assignee:
        d['assigneeEmail'] = t.assignee.email
        d['assigneeName'] = t.assignee.full_name
        d['assigneeRole'] = t.assignee.role
    d.update(extra)
    return d


# ── Auth ───────────────────────────────────────────────────────────────────
def current_staff():
    sid = session.get('staff_id')
    if not sid:
        return None
    return StaffUser.query.get(sid)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        staff = current_staff()
        if not staff or not staff.active:
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            staff = current_staff()
            if not staff or not staff.active:
                return redirect(url_for('admin.login'))
            if staff.role not in roles:
                return jsonify({'error': 'forbidden'}), 403
            return f(*args, **kwargs)
        return decorated
    return deco


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    # If a valid session already exists (e.g. the phone's back button
    # returned here after login), go straight to the dashboard instead of
    # showing the login form again — landing back on a login screen reads
    # as "I got logged out" even though the session is still fine.
    existing = current_staff()
    if existing and existing.active and request.method == 'GET':
        return redirect(url_for('admin.dashboard'))

    error = None
    lang = request.args.get('lang') or request.form.get('lang', 'ar')
    if request.method == 'POST':
        u = sanitize_text(request.form.get('username', ''))
        p = request.form.get('password', '')
        staff = StaffUser.query.filter(db_ilike(StaffUser.username, u)).first()
        if staff and staff.active and check_password_hash(staff.password_hash, p):
            session.permanent = True
            session['staff_id'] = staff.id
            session['admin_lang'] = lang
            staff.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('admin.dashboard'))
        error = 'بيانات خاطئة' if lang == 'ar' else 'Invalid credentials'
    return render_template('admin/login.html', error=error, lang=lang)


@admin_bp.route('/logout')
def logout():
    session.pop('staff_id', None)
    return redirect(url_for('admin.login'))


# ── Email action links ──────────────────────────────────────────────────────
# One-click links embedded in staff notification emails (new-ticket broadcast,
# assignment notice, etc). A link only authenticates the staff member named in
# the token and deep-links them into the dashboard, already focused on the
# relevant ticket/action — it never performs the action itself, so it stays
# safe to auto-fetch (email security scanners, link previews) and the exact
# same role checks the dashboard already enforces (can_manage_ticket /
# can_assign) decide what that staff member can actually do once there.
@admin_bp.route('/go/<token>')
def email_action_link(token):
    lang = session.get('admin_lang', 'ar')
    try:
        data = read_ticket_action_token(token)
    except ExpiredActionToken:
        msg = 'انتهت صلاحية هذا الرابط، يُرجى تسجيل الدخول' if lang == 'ar' else 'This link has expired — please log in'
        return render_template('admin/login.html', error=msg, lang=lang)
    except InvalidActionToken:
        return redirect(url_for('admin.login'))

    staff = StaffUser.query.get(data.get('sid'))
    ticket = Ticket.query.get(data.get('tid'))
    if not staff or not staff.active:
        msg = 'الحساب غير متاح، يُرجى تسجيل الدخول' if lang == 'ar' else 'That account is no longer available — please log in'
        return render_template('admin/login.html', error=msg, lang=lang)
    if not ticket:
        return redirect(url_for('admin.dashboard'))

    session.permanent = True
    session['staff_id'] = staff.id
    session.setdefault('admin_lang', lang)
    staff.last_login = datetime.utcnow()
    db.session.commit()

    focus = data.get('focus') or ''
    dest = url_for('admin.dashboard') + f'?ticket={ticket.id}' + (f'&focus={focus}' if focus else '')
    return redirect(dest)


@admin_bp.route('/')
@login_required
def dashboard():
    lang = session.get('admin_lang', 'ar')
    return render_template('admin/dashboard.html', lang=lang, me=current_staff().to_dict())


@admin_bp.route('/api/me')
@login_required
def api_me():
    return jsonify(current_staff().to_dict())


# ── Tickets: list / detail ─────────────────────────────────────────────────
@admin_bp.route('/api/tickets')
@login_required
def api_tickets():
    staff = current_staff()
    q = Ticket.query

    status = request.args.get('status', 'all')
    if status != 'all':
        q = q.filter_by(status=status)

    category_id = request.args.get('category_id', type=int)
    if category_id:
        q = q.filter_by(category_id=category_id)

    assignee_param = request.args.get('assignee_id')
    if assignee_param == 'unassigned':
        q = q.filter(Ticket.assignee_id.is_(None))
    elif assignee_param and assignee_param.isdigit():
        q = q.filter_by(assignee_id=int(assignee_param))

    if request.args.get('priority') in ('low', 'medium', 'high'):
        q = q.filter_by(priority=request.args.get('priority'))

    archived_param = request.args.get('archived', '0')
    if archived_param == '1':
        q = q.filter_by(archived=True)
    else:
        q = q.filter(Ticket.archived.isnot(True))

    if request.args.get('merged') != '1':
        q = q.filter(Ticket.merged_into_id.is_(None))

    # Technical Support only sees their own queue; System Admin / Administrator see everything.
    if staff.role == ROLE_TECH:
        q = q.filter_by(assignee_id=staff.id)

    search = request.args.get('q', '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(
            Ticket.subject.ilike(like), Ticket.teacher_name.ilike(like),
            Ticket.tracking_code.ilike(like),
            db.cast(Ticket.serial_number, db.String).ilike(like),
        ))

    tickets = q.order_by(Ticket.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tickets])


@admin_bp.route('/api/tickets/<int:ticket_id>')
@login_required
def api_ticket_detail(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    return jsonify(ticket.to_dict())


# ── Assign / Unassign / Reassign (System Admin & Administrator only) ──────
@admin_bp.route('/api/tickets/<int:ticket_id>/assign', methods=['POST'])
@login_required
def api_assign(ticket_id):
    staff = current_staff()
    if not staff.can_assign():
        return jsonify({'error': 'forbidden'}), 403
    ticket = Ticket.query.get_or_404(ticket_id)
    data = request.get_json(silent=True) or {}
    assignee_id = data.get('assigneeId')

    # Captured BEFORE any reassignment below, so we can notify whoever
    # is about to lose the ticket — otherwise they'd only find out by
    # stumbling onto it in the dashboard later.
    previous_assignee = ticket.assignee

    if assignee_id is None:
        ticket.assignee_id = None
        ticket.assigned_at = None
        db.session.commit()
        try:
            if previous_assignee and previous_assignee.email:
                send_ticket_reassigned_away(_ticket_email_ctx(
                    ticket, prevAssigneeEmail=previous_assignee.email, prevAssigneeName=previous_assignee.full_name))
        except Exception as e:
            print(f"[email] unassign notify failed: {e}", flush=True)
        return jsonify(ticket.to_dict())

    assignee = StaffUser.query.filter_by(id=assignee_id, active=True).first()
    if not assignee:
        return jsonify({'error': 'staff not found'}), 404

    ticket.assignee_id = assignee.id
    ticket.assigned_at = datetime.utcnow()
    ticket.reminder_sent = False
    if ticket.status == 'open':
        ticket.status = 'in_progress'
    db.session.add(TicketComment(
        ticket_id=ticket.id, author_role='system', author_name='',
        body=(f'تم تعيين التذكرة إلى {assignee.full_name}' if session.get('admin_lang', 'ar') == 'ar'
              else f'Ticket assigned to {assignee.full_name}'),
        internal=True, created_at=datetime.utcnow(),
    ))
    db.session.commit()

    try:
        if assignee.email:
            send_ticket_assigned(_ticket_email_ctx(ticket))
        from utils.push_utils import send_push_to_staff
        send_push_to_staff(current_app._get_current_object(), assignee.id,
                            'تذكرة جديدة معينة لك / New ticket assigned',
                            f"#{ticket.serial_number} — {ticket.subject}", '/admin/')
    except Exception as e:
        print(f"[email] assign notify failed: {e}", flush=True)

    # Notify whoever HAD it, only when it's actually moving to someone
    # else (skip a no-op "reassign" back to the same person).
    if previous_assignee and previous_assignee.id != assignee.id:
        try:
            if previous_assignee.email:
                send_ticket_reassigned_away(_ticket_email_ctx(
                    ticket, prevAssigneeEmail=previous_assignee.email, prevAssigneeName=previous_assignee.full_name),
                    new_assignee_name=assignee.full_name)
            from utils.push_utils import send_push_to_staff
            send_push_to_staff(current_app._get_current_object(), previous_assignee.id,
                                'نُقلت عنك تذكرة / Ticket reassigned away',
                                f"#{ticket.serial_number} — {ticket.subject}", '/admin/')
        except Exception as e:
            print(f"[email] reassign-away notify failed: {e}", flush=True)

    return jsonify(ticket.to_dict())


# ── Comment ─────────────────────────────────────────────────────────────────
@admin_bp.route('/api/tickets/<int:ticket_id>/comment', methods=['POST'])
@login_required
def api_comment(ticket_id):
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    internal = bool(data.get('internal'))
    if not body:
        return jsonify({'error': 'empty comment'}), 400

    comment = TicketComment(
        ticket_id=ticket.id, author_role='staff', author_name=staff.full_name,
        staff_id=staff.id, body=body, internal=internal, created_at=datetime.utcnow(),
    )
    db.session.add(comment)
    ticket.reminder_sent = False
    db.session.commit()

    if not internal:
        try:
            if ticket.teacher_email:
                send_new_comment_notification(_ticket_email_ctx(ticket), comment.to_dict(),
                                                ticket.teacher_email, ticket.teacher_name, to_teacher=True)
        except Exception as e:
            print(f"[email] comment notify failed: {e}", flush=True)
    else:
        try:
            emails = [s.email for s in StaffUser.query.filter(
                StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]),
                StaffUser.active.isnot(False), StaffUser.id != staff.id,
            ).all() if s.email]
            if emails:
                send_internal_note_notification(_ticket_email_ctx(ticket), comment.to_dict(), emails)
        except Exception as e:
            print(f"[email] internal note notify failed: {e}", flush=True)

    # Floating (Web Push) notification — previously only assignment/priority
    # changes triggered this, so a colleague adding a comment (public reply
    # OR internal note) never showed up as a live notification for anyone
    # else already in the dashboard. Notify the assignee (if any, and not
    # the author) plus every other System Admin/Administrator, for both
    # comment kinds — mirrors who already gets the internal-note EMAIL,
    # extended to public replies too.
    try:
        from utils.push_utils import send_push_to_staff
        push_title = (('ملاحظة داخلية جديدة / New internal note' if internal
                        else 'تعليق جديد / New comment') + f" — #{ticket.serial_number}")
        notify_ids = set()
        if ticket.assignee_id and ticket.assignee_id != staff.id:
            notify_ids.add(ticket.assignee_id)
        for s in StaffUser.query.filter(
            StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]),
            StaffUser.active.isnot(False), StaffUser.id != staff.id,
        ).all():
            notify_ids.add(s.id)
        app_obj = current_app._get_current_object()
        for sid in notify_ids:
            send_push_to_staff(app_obj, sid, push_title, body[:120], '/admin/')
    except Exception as e:
        print(f"[push] comment notify failed: {e}", flush=True)

    return jsonify(ticket.to_dict())


# ── Close / Reopen / Archive ────────────────────────────────────────────────
@admin_bp.route('/api/tickets/<int:ticket_id>/close', methods=['POST'])
@login_required
def api_close(ticket_id):
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    note = (data.get('comment') or '').strip()

    ticket.status = 'closed'
    ticket.closed_at = datetime.utcnow()
    if note:
        db.session.add(TicketComment(ticket_id=ticket.id, author_role='staff', author_name=staff.full_name,
                                      staff_id=staff.id, body=note, internal=False, created_at=datetime.utcnow()))
    db.session.add(TicketComment(
        ticket_id=ticket.id, author_role='system', author_name='',
        body=('تم إغلاق التذكرة' if session.get('admin_lang', 'ar') == 'ar' else 'Ticket closed'),
        internal=True, created_at=datetime.utcnow(),
    ))
    db.session.commit()

    try:
        if ticket.teacher_email:
            send_ticket_closed(_ticket_email_ctx(ticket))
    except Exception as e:
        print(f"[email] close notify failed: {e}", flush=True)

    return jsonify(ticket.to_dict())


@admin_bp.route('/api/tickets/<int:ticket_id>/reopen', methods=['POST'])
@login_required
def api_reopen(ticket_id):
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403

    ticket.status = 'in_progress' if ticket.assignee_id else 'open'
    ticket.reopened_at = datetime.utcnow()
    ticket.archived = False
    ticket.reminder_sent = False
    db.session.add(TicketComment(
        ticket_id=ticket.id, author_role='system', author_name='',
        body=('تم إعادة فتح التذكرة' if session.get('admin_lang', 'ar') == 'ar' else 'Ticket reopened'),
        internal=True, created_at=datetime.utcnow(),
    ))
    db.session.commit()

    try:
        if ticket.teacher_email:
            send_ticket_reopened(_ticket_email_ctx(ticket))
    except Exception as e:
        print(f"[email] reopen notify failed: {e}", flush=True)

    return jsonify(ticket.to_dict())


@admin_bp.route('/api/tickets/<int:ticket_id>/wait', methods=['POST'])
@login_required
def api_wait(ticket_id):
    """Marks a ticket as waiting — typically because staff is waiting on a
    reply or more information from the requester."""
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403
    if ticket.status == 'closed':
        return jsonify({'error': 'a closed ticket cannot be marked as waiting'}), 400
    ticket.status = 'waiting'
    db.session.add(TicketComment(
        ticket_id=ticket.id, author_role='system', author_name='',
        body=('تم وضع التذكرة كمعلقة' if session.get('admin_lang', 'ar') == 'ar' else 'Ticket set to waiting'),
        internal=True, created_at=datetime.utcnow(),
    ))
    db.session.commit()
    return jsonify(ticket.to_dict())


@admin_bp.route('/api/tickets/<int:ticket_id>/resume', methods=['POST'])
@login_required
def api_resume(ticket_id):
    """Brings a waiting ticket back to active follow-up."""
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403
    ticket.status = 'in_progress' if ticket.assignee_id else 'open'
    ticket.reminder_sent = False
    db.session.add(TicketComment(
        ticket_id=ticket.id, author_role='system', author_name='',
        body=('تم استئناف متابعة التذكرة' if session.get('admin_lang', 'ar') == 'ar' else 'Ticket follow-up resumed'),
        internal=True, created_at=datetime.utcnow(),
    ))
    db.session.commit()
    return jsonify(ticket.to_dict())


@admin_bp.route('/api/tickets/<int:ticket_id>/priority', methods=['POST'])
@login_required
def api_set_priority(ticket_id):
    """Staff-controlled priority (default Medium at creation). Notifies the
    assignee, if any, when the priority changes."""
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket) or not staff.can_set_priority():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    priority = data.get('priority')
    if priority not in PRIORITIES:
        return jsonify({'error': 'invalid priority'}), 400

    old_priority = ticket.priority
    if priority == old_priority:
        return jsonify(ticket.to_dict())

    ticket.priority = priority
    lang = session.get('admin_lang', 'ar')
    labels_ar = {'low': 'منخفضة', 'medium': 'متوسطة', 'high': 'عالية'}
    labels_en = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}
    note = (f'تم تغيير الأولوية إلى {labels_ar[priority]}' if lang == 'ar'
            else f'Priority changed to {labels_en[priority]}')
    db.session.add(TicketComment(ticket_id=ticket.id, author_role='system', author_name='',
                                  body=note, internal=True, created_at=datetime.utcnow()))
    db.session.commit()

    try:
        if ticket.assignee_id and ticket.assignee and ticket.assignee.email:
            ctx = _ticket_email_ctx(ticket, priorityLabelAr=labels_ar[priority], priorityLabelEn=labels_en[priority])
            send_priority_changed(ctx)
        if ticket.assignee_id:
            from utils.push_utils import send_push_to_staff
            send_push_to_staff(current_app._get_current_object(), ticket.assignee_id,
                                'تغيّرت أولوية التذكرة / Priority changed',
                                f"#{ticket.serial_number} — {labels_ar[priority]}/{labels_en[priority]}", '/admin/')
    except Exception as e:
        print(f"[email] priority-change notify failed: {e}", flush=True)

    return jsonify(ticket.to_dict())


@admin_bp.route('/api/tickets/<int:ticket_id>/archive', methods=['POST'])
@login_required
def api_archive(ticket_id):
    staff = current_staff()
    ticket = Ticket.query.get_or_404(ticket_id)
    if not staff.can_manage_ticket(ticket):
        return jsonify({'error': 'forbidden'}), 403
    if ticket.status != 'closed':
        return jsonify({'error': 'only closed tickets can be archived'}), 400
    ticket.archived = True
    db.session.commit()
    return jsonify(ticket.to_dict())


# ── Merge (keeps the LOWER serial number, cancels the other) ──────────────
@admin_bp.route('/api/tickets/merge', methods=['POST'])
@login_required
def api_merge():
    staff = current_staff()
    data = request.get_json(silent=True) or {}
    id_a, id_b = data.get('ticketIdA'), data.get('ticketIdB')
    if not id_a or not id_b or id_a == id_b:
        return jsonify({'error': 'two different tickets are required'}), 400

    a = Ticket.query.get_or_404(id_a)
    b = Ticket.query.get_or_404(id_b)

    if not (staff.can_manage_ticket(a) and staff.can_manage_ticket(b)):
        return jsonify({'error': 'forbidden'}), 403
    if a.merged_into_id or b.merged_into_id:
        return jsonify({'error': 'a merged ticket cannot be merged again'}), 400

    keep, drop = (a, b) if a.serial_number < b.serial_number else (b, a)

    drop.merged_into_id = keep.id
    drop.status = 'closed'
    drop.closed_at = datetime.utcnow()
    drop.archived = True

    lang = session.get('admin_lang', 'ar')
    note_keep = (f'تم دمج التذكرة #{drop.serial_number} مع هذه التذكرة (تم إلغاء رقمها).' if lang == 'ar'
                 else f'Ticket #{drop.serial_number} was merged into this one (its number was cancelled).')
    note_drop = (f'تم دمج هذه التذكرة مع التذكرة #{keep.serial_number} والمتابعة ستكون من خلالها.' if lang == 'ar'
                 else f'This ticket was merged into ticket #{keep.serial_number}; follow-up continues there.')
    db.session.add(TicketComment(ticket_id=keep.id, author_role='system', author_name='',
                                  body=note_keep, internal=True, created_at=datetime.utcnow()))
    db.session.add(TicketComment(ticket_id=drop.id, author_role='system', author_name='',
                                  body=note_drop, internal=True, created_at=datetime.utcnow()))
    db.session.commit()

    try:
        if drop.teacher_email:
            send_ticket_merged(_ticket_email_ctx(drop), keep.serial_number, keep.tracking_code)
    except Exception as e:
        print(f"[email] merge notify failed: {e}", flush=True)

    return jsonify({'kept': keep.to_dict(), 'dropped': drop.to_dict()})


# ── Categories & Category Items (System Admin & Administrator) ─────────────
@admin_bp.route('/api/categories')
@login_required
def api_get_categories():
    cats = Category.query.order_by(Category.sort_order).all()
    return jsonify([c.to_dict(with_items=True) for c in cats])


@admin_bp.route('/api/categories', methods=['POST'])
@login_required
def api_add_category():
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    name_ar = sanitize_text(data.get('nameAr'))
    if not name_ar:
        return jsonify({'error': 'nameAr required'}), 400
    cat = Category(name_ar=name_ar, name_en=sanitize_text(data.get('nameEn')) or None,
                    active=True, sort_order=Category.query.count())
    db.session.add(cat)
    db.session.commit()
    return jsonify(cat.to_dict())


@admin_bp.route('/api/categories/<int:cat_id>', methods=['PUT'])
@login_required
def api_edit_category(cat_id):
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    cat = Category.query.get_or_404(cat_id)
    data = request.get_json(silent=True) or {}
    if 'nameAr' in data:
        cat.name_ar = sanitize_text(data['nameAr']) or cat.name_ar
    if 'nameEn' in data:
        cat.name_en = sanitize_text(data['nameEn'])
    if 'active' in data:
        cat.active = bool(data['active'])
    db.session.commit()
    return jsonify(cat.to_dict())


@admin_bp.route('/api/categories/<int:cat_id>', methods=['DELETE'])
@login_required
def api_delete_category(cat_id):
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/categories/<int:cat_id>/items', methods=['POST'])
@login_required
def api_add_category_item(cat_id):
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    Category.query.get_or_404(cat_id)
    data = request.get_json(silent=True) or {}
    name_ar = sanitize_text(data.get('nameAr'))
    if not name_ar:
        return jsonify({'error': 'nameAr required'}), 400
    item = CategoryItem(category_id=cat_id, code=sanitize_text(data.get('code')),
                         code_en=sanitize_text(data.get('codeEn')),
                         name_ar=name_ar, name_en=sanitize_text(data.get('nameEn')) or None,
                         active=True, sort_order=CategoryItem.query.filter_by(category_id=cat_id).count())
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict())


@admin_bp.route('/api/category-items/<int:item_id>', methods=['PUT'])
@login_required
def api_edit_category_item(item_id):
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    item = CategoryItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    if 'nameAr' in data:
        item.name_ar = sanitize_text(data['nameAr']) or item.name_ar
    if 'nameEn' in data:
        item.name_en = sanitize_text(data['nameEn'])
    if 'code' in data:
        item.code = sanitize_text(data['code'])
    if 'codeEn' in data:
        item.code_en = sanitize_text(data['codeEn'])
    if 'active' in data:
        item.active = bool(data['active'])
    db.session.commit()
    return jsonify(item.to_dict())


@admin_bp.route('/api/category-items/<int:item_id>', methods=['DELETE'])
@login_required
def api_delete_category_item(item_id):
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    item = CategoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})


# ── Teacher roster ───────────────────────────────────────────────────────
@admin_bp.route('/api/teachers')
@login_required
def api_get_teachers():
    # Guest/external rows (auto-created when "accept external submitters" is
    # on) are intentionally excluded — this is the approved roster, not a
    # log of every requester.
    teachers = Teacher.query.filter(Teacher.external.isnot(True)).order_by(Teacher.name).all()
    return jsonify([t.to_dict() for t in teachers])


@admin_bp.route('/api/bulk-add-teachers', methods=['POST'])
@login_required
def api_bulk_add_teachers():
    """Accepts {list: [{name, email, phone, department}, ...]} — used by the
    Teachers tab's CSV/TXT upload (one 'name,email,phone' per line)."""
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    items = data.get('list') or []
    count, errors = 0, []
    for row in items:
        name = sanitize_text(row.get('name'))
        if not name:
            errors.append(row)
            continue
        if Teacher.query.filter(Teacher.external.isnot(True)).filter(db_ilike(Teacher.name, name)).first():
            errors.append(row)  # already exists — skipped, not overwritten
            continue
        db.session.add(Teacher(
            name=name, email=sanitize_text(row.get('email')),
            phone=sanitize_text(row.get('phone')), department=sanitize_text(row.get('department')),
            active=True,
        ))
        count += 1
    db.session.commit()
    return jsonify({'success': True, 'count': count, 'errors': errors})


@admin_bp.route('/api/bulk-add-categories', methods=['POST'])
@login_required
def api_bulk_add_categories():
    """Accepts {list: [{nameAr, nameEn}, ...]} — used by the Categories
    tab's CSV/TXT upload (one 'nameAr,nameEn' per line)."""
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    items = data.get('list') or []
    count, errors = 0, []
    base = Category.query.count()
    for i, row in enumerate(items):
        name_ar = sanitize_text(row.get('nameAr'))
        if not name_ar:
            errors.append(row)
            continue
        db.session.add(Category(name_ar=name_ar, name_en=sanitize_text(row.get('nameEn')) or None,
                                 active=True, sort_order=base + i))
        count += 1
    db.session.commit()
    return jsonify({'success': True, 'count': count, 'errors': errors})


@admin_bp.route('/api/categories/<int:cat_id>/bulk-add-items', methods=['POST'])
@login_required
def api_bulk_add_category_items(cat_id):
    """Accepts {list: [{nameAr, nameEn, code}, ...]} for one category —
    used by the Categories tab's per-category CSV/TXT upload."""
    staff = current_staff()
    if not staff.can_manage_categories():
        return jsonify({'error': 'forbidden'}), 403
    Category.query.get_or_404(cat_id)
    data = request.get_json(silent=True) or {}
    items = data.get('list') or []
    count, errors = 0, []
    base = CategoryItem.query.filter_by(category_id=cat_id).count()
    for i, row in enumerate(items):
        name_ar = sanitize_text(row.get('nameAr'))
        if not name_ar:
            errors.append(row)
            continue
        db.session.add(CategoryItem(category_id=cat_id, code=sanitize_text(row.get('code')),
                                     code_en=sanitize_text(row.get('codeEn')),
                                     name_ar=name_ar, name_en=sanitize_text(row.get('nameEn')) or None,
                                     active=True, sort_order=base + i))
        count += 1
    db.session.commit()
    return jsonify({'success': True, 'count': count, 'errors': errors})


@admin_bp.route('/api/teachers', methods=['POST'])
@login_required
def api_add_teacher():
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    name = sanitize_text(data.get('name'))
    if not name:
        return jsonify({'error': 'name required'}), 400
    teacher = Teacher(name=name, email=sanitize_text(data.get('email')),
                       phone=sanitize_text(data.get('phone')), department=sanitize_text(data.get('department')),
                       active=True)
    db.session.add(teacher)
    db.session.commit()
    return jsonify(teacher.to_dict())


@admin_bp.route('/api/teachers/<int:teacher_id>', methods=['PUT'])
@login_required
def api_edit_teacher(teacher_id):
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    teacher = Teacher.query.get_or_404(teacher_id)
    data = request.get_json(silent=True) or {}
    for field in ('name', 'email', 'phone', 'department'):
        if field in data:
            setattr(teacher, field, sanitize_text(data[field]))
    if 'active' in data:
        teacher.active = bool(data['active'])
    db.session.commit()
    return jsonify(teacher.to_dict())


@admin_bp.route('/api/teachers/<int:teacher_id>', methods=['DELETE'])
@login_required
def api_delete_teacher(teacher_id):
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    teacher = Teacher.query.get_or_404(teacher_id)
    db.session.delete(teacher)
    db.session.commit()
    return jsonify({'success': True})


# ── Staff accounts (Administrator only) ─────────────────────────────────────
@admin_bp.route('/api/staff')
@login_required
def api_get_staff():
    staff_list = StaffUser.query.order_by(StaffUser.full_name).all()
    return jsonify([s.to_dict() for s in staff_list])


@admin_bp.route('/api/staff', methods=['POST'])
@role_required(ROLE_ADMINISTRATOR)
def api_add_staff():
    data = request.get_json(silent=True) or {}
    username = sanitize_text(data.get('username'))
    full_name = sanitize_text(data.get('fullName'))
    password = data.get('password') or ''
    role = data.get('role')
    if not username or not full_name or not password or role not in ALL_ROLES:
        return jsonify({'error': 'username, fullName, password and a valid role are required'}), 400
    if StaffUser.query.filter(db_ilike(StaffUser.username, username)).first():
        return jsonify({'error': 'username already exists'}), 400
    email = sanitize_text(data.get('email'))
    staff = StaffUser(username=username, full_name=full_name,
                       password_hash=generate_password_hash(password),
                       email=email, role=role, active=True,
                       can_change_priority=bool(data.get('canChangePriority')),
                       can_manage_reminders=bool(data.get('canManageReminders')))
    db.session.add(staff)
    db.session.commit()

    if email:
        try:
            send_new_staff_account_email(staff.to_dict(), password)
        except Exception as e:
            print(f"[email] new staff account email failed: {e}", flush=True)

    return jsonify(staff.to_dict())


@admin_bp.route('/api/staff/<int:staff_id>', methods=['PUT'])
@role_required(ROLE_ADMINISTRATOR)
def api_edit_staff(staff_id):
    staff = StaffUser.query.get_or_404(staff_id)
    data = request.get_json(silent=True) or {}
    if 'fullName' in data:
        staff.full_name = sanitize_text(data['fullName']) or staff.full_name
    if 'email' in data:
        staff.email = sanitize_text(data['email'])
    if 'role' in data and data['role'] in ALL_ROLES:
        staff.role = data['role']
    if 'active' in data:
        if staff.id == session.get('staff_id') and not data['active']:
            return jsonify({'error': "cannot deactivate your own account"}), 400
        staff.active = bool(data['active'])
    if data.get('password'):
        staff.password_hash = generate_password_hash(data['password'])
    if 'canChangePriority' in data:
        staff.can_change_priority = bool(data['canChangePriority'])
    if 'canManageReminders' in data:
        staff.can_manage_reminders = bool(data['canManageReminders'])
    db.session.commit()
    return jsonify(staff.to_dict())


@admin_bp.route('/api/staff/<int:staff_id>', methods=['DELETE'])
@role_required(ROLE_ADMINISTRATOR)
def api_delete_staff(staff_id):
    if staff_id == session.get('staff_id'):
        return jsonify({'error': 'cannot delete your own account'}), 400
    staff = StaffUser.query.get_or_404(staff_id)
    if staff.role == ROLE_ADMINISTRATOR and StaffUser.query.filter_by(role=ROLE_ADMINISTRATOR, active=True).count() <= 1:
        return jsonify({'error': 'at least one active Administrator must remain'}), 400
    # Every FK that points at staff_users.id has to be cleared/removed
    # first, or the delete below fails with a 500 (IntegrityError) the
    # moment this staff member has ever been assigned a ticket, posted a
    # comment, or registered a push subscription.
    Ticket.query.filter_by(assignee_id=staff.id).update({'assignee_id': None})
    TicketComment.query.filter_by(staff_id=staff.id).update({'staff_id': None})
    PushSubscription.query.filter_by(staff_id=staff.id).delete()
    db.session.delete(staff)
    db.session.commit()
    return jsonify({'success': True})


# ── Web Push subscription (staff PWA) ──────────────────────────────────────
@admin_bp.route('/api/push-subscribe', methods=['POST'])
@login_required
def api_push_subscribe():
    staff = current_staff()
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    keys = data.get('keys') or {}
    if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
        return jsonify({'error': 'invalid subscription'}), 400
    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub = PushSubscription(endpoint=endpoint)
        db.session.add(sub)
    sub.staff_id = staff.id
    sub.p256dh = keys['p256dh']
    sub.auth = keys['auth']
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/set-lang', methods=['POST'])
@login_required
def api_set_lang():
    """Keeps the server-side session in sync with the language toggled
    inside the dashboard, so the language chosen on the login page (or
    last toggled in-app) is what a fresh login/reload actually shows —
    a stale client-only preference should never silently override it."""
    data = request.get_json(silent=True) or {}
    if data.get('lang') in ('ar', 'en'):
        session['admin_lang'] = data['lang']
    return jsonify({'lang': session.get('admin_lang', 'ar')})


@admin_bp.route('/api/vapid-public-key')
@login_required
def api_vapid_public_key():
    return jsonify({'key': current_app.config.get('VAPID_PUBLIC_KEY', '')})


# ── System settings ─────────────────────────────────────────────────────
@admin_bp.route('/api/settings')
@login_required
def api_get_settings():
    return jsonify({'allowExternalSubmitters': get_setting('allow_external_submitters', '0') == '1'})


@admin_bp.route('/api/settings', methods=['POST'])
@login_required
def api_set_settings():
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    if 'allowExternalSubmitters' in data:
        set_setting('allow_external_submitters', '1' if data['allowExternalSubmitters'] else '0')
    return jsonify({'allowExternalSubmitters': get_setting('allow_external_submitters', '0') == '1'})


# ── Auto reminder for unprocessed tickets ───────────────────────────────────
@admin_bp.route('/api/reminder-settings')
@login_required
def api_get_reminder_settings():
    return jsonify({
        'enabled': get_setting('auto_reminder_enabled', '0') == '1',
        'hours': int(float(get_setting('auto_reminder_hours', '24') or 24)),
    })


@admin_bp.route('/api/reminder-settings', methods=['POST'])
@login_required
def api_set_reminder_settings():
    staff = current_staff()
    if not staff.is_system_admin_or_above() or not staff.can_manage_reminder_settings():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        set_setting('auto_reminder_enabled', '1' if data['enabled'] else '0')
    if 'hours' in data:
        try:
            hours = max(1, min(720, int(data['hours'])))
            set_setting('auto_reminder_hours', str(hours))
        except (TypeError, ValueError):
            pass
    return jsonify({
        'enabled': get_setting('auto_reminder_enabled', '0') == '1',
        'hours': int(float(get_setting('auto_reminder_hours', '24') or 24)),
    })


@admin_bp.route('/api/reminder-check-now', methods=['POST'])
@login_required
def api_reminder_check_now():
    """Lets a System Admin/Administrator trigger a check on demand
    (useful for testing, without waiting for the external cron)."""
    staff = current_staff()
    if not staff.is_system_admin_or_above() or not staff.can_manage_reminder_settings():
        return jsonify({'error': 'forbidden'}), 403
    from utils.reminder_utils import check_and_send_reminders
    return jsonify(check_and_send_reminders())


@admin_bp.route('/api/tickets/reminder-toggle', methods=['POST'])
@login_required
def api_tickets_reminder_toggle():
    """Opts a set of tickets in/out of the auto-reminder sweep — this is
    the per-ticket (multi-select) control; it does NOT touch every
    ticket, only the ids given. Any System Admin/Administrator/Technical
    Support can flip it on tickets they can otherwise manage."""
    data = request.get_json(silent=True) or {}
    ids = data.get('ticketIds') or []
    enabled = bool(data.get('enabled'))
    if not isinstance(ids, list) or not ids:
        return jsonify({'error': 'ticketIds required'}), 400
    staff = current_staff()
    q = Ticket.query.filter(Ticket.id.in_(ids))
    if not staff.is_system_admin_or_above():
        q = q.filter(Ticket.assignee_id == staff.id)  # Technical Support: own tickets only
    tickets = q.all()
    for tk in tickets:
        tk.reminder_enabled = enabled
        if enabled:
            tk.reminder_sent = False  # opting back in should be able to fire again
    db.session.commit()
    return jsonify({'updated': len(tickets)})


# ── Scrolling ticker (global announcement marquee) ─────────────────────────
@admin_bp.route('/api/ticker-settings')
@login_required
def api_get_ticker_settings():
    from utils.ticker_utils import get_ticker_config
    return jsonify(get_ticker_config())


@admin_bp.route('/api/ticker-settings', methods=['POST'])
@login_required
def api_set_ticker_settings():
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    from utils.ticker_utils import set_ticker_config
    data = request.get_json(silent=True) or {}
    cfg = {}
    if 'enabled' in data:
        cfg['enabled'] = bool(data['enabled'])
    if 'html' in data:
        cfg['html'] = data['html'] or ''
    if 'htmlEn' in data:
        cfg['htmlEn'] = data['htmlEn'] or ''
    if 'speedSeconds' in data:
        try:
            cfg['speedSeconds'] = max(5, min(180, int(data['speedSeconds'])))
        except (TypeError, ValueError):
            pass
    if 'pulse' in data:
        cfg['pulse'] = bool(data['pulse'])
    if 'pulseSeconds' in data:
        try:
            cfg['pulseSeconds'] = max(0.3, min(10, float(data['pulseSeconds'])))
        except (TypeError, ValueError):
            pass
    if data.get('textShadow') in ('none', 'light', 'strong'):
        cfg['textShadow'] = data['textShadow']
    if 'rssColor' in data:
        color = sanitize_text(data['rssColor'])
        if re.fullmatch(r'#[0-9a-fA-F]{6}', color or ''):
            cfg['rssColor'] = color
    if 'rssBold' in data:
        cfg['rssBold'] = bool(data['rssBold'])
    if 'rssFontSize' in data:
        try:
            cfg['rssFontSize'] = max(10, min(40, int(data['rssFontSize'])))
        except (TypeError, ValueError):
            pass
    if 'logoBetween' in data:
        cfg['logoBetween'] = bool(data['logoBetween'])
    if 'rssUrl' in data:
        cfg['rssUrl'] = sanitize_text(data['rssUrl'])
    return jsonify(set_ticker_config(cfg))


# ── Reports (evaluation): staff ← criteria, filterable, printable ─────────
def _build_reports_data(date_from, date_to, category_id, status, priority):
    q = Ticket.query.filter(Ticket.merged_into_id.is_(None))
    if date_from:
        try:
            q = q.filter(Ticket.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Ticket.created_at < datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        except ValueError:
            pass
    if category_id:
        q = q.filter_by(category_id=category_id)
    if status in ('open', 'in_progress', 'waiting', 'closed'):
        q = q.filter_by(status=status)
    if priority in PRIORITIES:
        q = q.filter_by(priority=priority)

    tickets = q.all()

    def bucket(ts):
        by_status = {'open': 0, 'in_progress': 0, 'waiting': 0, 'closed': 0}
        by_priority = {'low': 0, 'medium': 0, 'high': 0}
        by_category, by_month = {}, {}
        close_hours = []
        for t in ts:
            by_status[t.status] = by_status.get(t.status, 0) + 1
            by_priority[t.priority or 'medium'] = by_priority.get(t.priority or 'medium', 0) + 1
            cat = t.category_name or '—'
            by_category[cat] = by_category.get(cat, 0) + 1
            month_key = t.created_at.strftime('%Y-%m') if t.created_at else '—'
            by_month[month_key] = by_month.get(month_key, 0) + 1
            if t.status == 'closed' and t.closed_at and t.created_at:
                close_hours.append((t.closed_at - t.created_at).total_seconds() / 3600)
        return {
            'total': len(ts), 'byStatus': by_status, 'byPriority': by_priority,
            'byCategory': dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
            'byMonth': dict(sorted(by_month.items())),
            'avgCloseHours': round(sum(close_hours) / len(close_hours), 1) if close_hours else None,
        }

    per_staff = defaultdict(list)
    unassigned_tickets = []
    for t in tickets:
        (per_staff[t.assignee_id] if t.assignee_id else unassigned_tickets).append(t)

    staff_rows = []
    for s in StaffUser.query.order_by(StaffUser.full_name).all():
        row = bucket(per_staff.get(s.id, []))
        row.update({'staffId': s.id, 'fullName': s.full_name, 'role': s.role, 'active': s.active})
        staff_rows.append(row)
    staff_rows.sort(key=lambda r: -r['total'])

    return {
        'overall': bucket(tickets),
        'staff': staff_rows,
        'unassigned': bucket(unassigned_tickets),
        'filters': {'from': date_from or '', 'to': date_to or '', 'categoryId': category_id,
                    'status': status or 'all', 'priority': priority or 'all'},
    }


@admin_bp.route('/api/reports')
@login_required
def api_reports():
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return jsonify({'error': 'forbidden'}), 403
    data = _build_reports_data(
        request.args.get('from'), request.args.get('to'),
        request.args.get('category_id', type=int),
        request.args.get('status'), request.args.get('priority'),
    )
    return jsonify(data)


@admin_bp.route('/reports/print')
@login_required
def print_reports():
    staff = current_staff()
    if not staff.is_system_admin_or_above():
        return redirect(url_for('admin.dashboard'))
    lang = session.get('admin_lang', 'ar')
    data = _build_reports_data(
        request.args.get('from'), request.args.get('to'),
        request.args.get('category_id', type=int),
        request.args.get('status'), request.args.get('priority'),
    )
    staff_id = request.args.get('staff_id', type=int)
    if staff_id:
        data['staff'] = [r for r in data['staff'] if r['staffId'] == staff_id]
    categories = Category.query.order_by(Category.sort_order).all()
    cat_name = None
    if data['filters']['categoryId']:
        cat = Category.query.get(data['filters']['categoryId'])
        cat_name = (cat.name_ar if lang == 'ar' else (cat.name_en or cat.name_ar)) if cat else None
    return render_template('admin/print_reports.html', lang=lang, data=data, cat_name=cat_name,
                            generated_at=datetime.utcnow(), categories=categories,
                            status_ar=STATUS_LABELS_AR, status_en=STATUS_LABELS_EN)


# ── Print view ───────────────────────────────────────────────────────────
@admin_bp.route('/ticket/<int:ticket_id>/print')
@login_required
def print_ticket(ticket_id):
    lang = session.get('admin_lang', 'ar')
    ticket = Ticket.query.get_or_404(ticket_id)
    return render_template('admin/print_ticket.html', lang=lang, ticket=ticket.to_dict(),
                            status_ar=STATUS_LABELS_AR, status_en=STATUS_LABELS_EN)
