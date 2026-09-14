from datetime import datetime
from flask import (Blueprint, render_template, request, jsonify,
                    redirect, url_for, current_app, send_from_directory, flash)
from models import (db, Ticket, TicketComment, Teacher, Category, CategoryItem,
                     gen_serial_number, gen_tracking_code)
from utils.helpers import is_valid_email, sanitize_text, save_upload, match_teacher, db_ilike
from utils.email_utils import send_ticket_confirmation, send_new_comment_notification, send_staff_new_ticket_notification

public_bp = Blueprint('public', __name__)


STATUS_LABELS_AR = {'open': 'مفتوحة', 'in_progress': 'قيد المعالجة', 'closed': 'مغلقة'}
STATUS_LABELS_EN = {'open': 'Open', 'in_progress': 'In Progress', 'closed': 'Closed'}


def _lang():
    return request.args.get('lang') or request.cookies.get('lang', 'ar')


def _ticket_email_ctx(t):
    d = t.to_dict()
    d['statusLabelAr'] = STATUS_LABELS_AR.get(t.status, t.status)
    d['statusLabelEn'] = STATUS_LABELS_EN.get(t.status, t.status)
    return d


# ── Landing ──────────────────────────────────────────────────────────────
@public_bp.route('/')
def index():
    lang = _lang()
    return render_template('index.html', lang=lang)


# ── Ticket submission form ────────────────────────────────────────────────
@public_bp.route('/ticket', methods=['GET', 'POST'])
def new_ticket():
    lang = _lang()

    if request.method == 'GET':
        categories = Category.query.filter_by(active=True).order_by(Category.sort_order).all()
        return render_template('ticket_form.html', lang=lang,
                                categories=[c.to_dict(with_items=True) for c in categories])

    # ── POST: validate & create ──────────────────────────────────────
    teacher_name = sanitize_text(request.form.get('teacher_name'))
    category_id = request.form.get('category_id', type=int)
    category_item_id = request.form.get('category_item_id', type=int) or None
    subject = sanitize_text(request.form.get('subject'))
    description = (request.form.get('description') or '').strip()
    location = sanitize_text(request.form.get('location'))

    errors = {}

    teacher = match_teacher(teacher_name)
    if not teacher:
        errors['teacher_name'] = (
            'اسم المعلم/ة غير موجود ضمن قائمة المعلمين المعتمدة. يرجى التواصل مع الإدارة لإضافتك '
            'إلى القائمة قبل تقديم طلب الدعم.' if lang == 'ar' else
            'This name is not on the approved teacher list. Please contact the administration to '
            'be added to the list before submitting a ticket.'
        )

    category = Category.query.get(category_id) if category_id else None
    if not category:
        errors['category_id'] = 'الرجاء اختيار تصنيف' if lang == 'ar' else 'Please choose a category'

    category_item = None
    if category and category_item_id:
        category_item = CategoryItem.query.filter_by(id=category_item_id, category_id=category.id).first()
    elif category and category.items:
        errors['category_item_id'] = ('الرجاء اختيار تحديد فرعي للتصنيف' if lang == 'ar'
                                       else 'Please choose a category item')

    if not subject:
        errors['subject'] = 'الرجاء كتابة موضوع مختصر للمشكلة' if lang == 'ar' else 'Please provide a short subject'

    if errors:
        categories = Category.query.filter_by(active=True).order_by(Category.sort_order).all()
        return render_template('ticket_form.html', lang=lang, errors=errors,
                                form=request.form,
                                categories=[c.to_dict(with_items=True) for c in categories]), 400

    attachments = []
    for f in request.files.getlist('attachments')[:5]:
        url = save_upload(f)
        if url:
            attachments.append(url)

    ticket = Ticket(
        serial_number=gen_serial_number(),
        tracking_code=gen_tracking_code(),
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        teacher_email=teacher.email,
        teacher_phone=teacher.phone,
        category_id=category.id,
        category_name=category.name_ar,
        category_item_id=category_item.id if category_item else None,
        category_item_name=category_item.name_ar if category_item else None,
        subject=subject,
        description=description,
        location=location,
        urgent=bool(request.form.get('urgent')),
        attachments=','.join(attachments),
        status='open',
        created_at=datetime.utcnow(),
    )
    db.session.add(ticket)
    db.session.commit()

    try:
        if teacher.email:
            send_ticket_confirmation(_ticket_email_ctx(ticket))
    except Exception as e:
        print(f"[email] ticket confirmation failed: {e}", flush=True)

    try:
        from models import StaffUser, ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR
        staff_emails = [s.email for s in StaffUser.query.filter(
            StaffUser.role.in_([ROLE_SYSTEM_ADMIN, ROLE_ADMINISTRATOR]), StaffUser.active.isnot(False)
        ).all() if s.email]
        if staff_emails:
            send_staff_new_ticket_notification(_ticket_email_ctx(ticket), staff_emails)
    except Exception as e:
        print(f"[email] staff new-ticket notification failed: {e}", flush=True)

    try:
        from utils.push_utils import send_push_to_all
        send_push_to_all(current_app._get_current_object(),
                          'تذكرة جديدة / New Ticket', f"#{ticket.serial_number} — {subject}", '/admin/')
    except Exception:
        pass

    return redirect(url_for('public.ticket_status', tracking_code=ticket.tracking_code, lang=lang, submitted=1))


# ── Lookup (by tracking code) ─────────────────────────────────────────────
@public_bp.route('/lookup', methods=['GET', 'POST'])
def lookup():
    lang = _lang()
    error = None
    if request.method == 'POST':
        code = sanitize_text(request.form.get('tracking_code', '')).upper()
        ticket = Ticket.query.filter_by(tracking_code=code).first()
        if ticket:
            return redirect(url_for('public.ticket_status', tracking_code=ticket.tracking_code, lang=lang))
        error = 'لا توجد تذكرة بهذا الرقم' if lang == 'ar' else 'No ticket found with this code'
    return render_template('lookup.html', lang=lang, error=error)


@public_bp.route('/ticket/<tracking_code>')
def ticket_status(tracking_code):
    lang = _lang()
    ticket = Ticket.query.filter_by(tracking_code=tracking_code.upper()).first_or_404()
    return render_template('ticket_status.html', lang=lang, ticket=ticket.to_dict(include_internal=False),
                            submitted=request.args.get('submitted') == '1',
                            status_ar=STATUS_LABELS_AR, status_en=STATUS_LABELS_EN)


@public_bp.route('/ticket/<tracking_code>/comment', methods=['POST'])
def add_public_comment(tracking_code):
    lang = _lang()
    ticket = Ticket.query.filter_by(tracking_code=tracking_code.upper()).first_or_404()
    body = (request.form.get('body') or '').strip()
    if body:
        comment = TicketComment(
            ticket_id=ticket.id, author_role='teacher', author_name=ticket.teacher_name,
            body=body, internal=False, created_at=datetime.utcnow(),
        )
        db.session.add(comment)
        db.session.commit()

        try:
            if ticket.assignee and ticket.assignee.email:
                send_new_comment_notification(_ticket_email_ctx(ticket), comment.to_dict(),
                                                ticket.assignee.email, ticket.assignee.full_name)
            if ticket.assignee_id:
                from utils.push_utils import send_push_to_staff
                send_push_to_staff(current_app._get_current_object(), ticket.assignee_id,
                                    f"تعليق جديد / New comment — #{ticket.serial_number}", body[:120], '/admin/')
        except Exception as e:
            print(f"[email] comment notify failed: {e}", flush=True)

    return redirect(url_for('public.ticket_status', tracking_code=ticket.tracking_code, lang=lang))


# ── Autocomplete / classification data (used by the ticket form's JS) ────
@public_bp.route('/api/teacher-names')
def api_teacher_names():
    q = request.args.get('q', '').strip()
    query = Teacher.query.filter(Teacher.active.isnot(False))
    if q:
        query = query.filter(Teacher.name.ilike(f'%{q}%'))
    names = [t.name for t in query.order_by(Teacher.name).limit(20).all()]
    return jsonify(names)


@public_bp.route('/api/teacher-lookup')
def api_teacher_lookup():
    """Used by the ticket form once a name is picked from the dropdown: if
    it's an exact match on the roster, returns the teacher's email so the
    form can show/confirm it automatically."""
    name = request.args.get('name', '')
    teacher = match_teacher(name)
    if not teacher:
        return jsonify({'found': False})
    return jsonify({'found': True, 'email': teacher.email or '', 'phone': teacher.phone or ''})


@public_bp.route('/api/categories')
def api_categories():
    categories = Category.query.filter_by(active=True).order_by(Category.sort_order).all()
    return jsonify([c.to_dict(with_items=True) for c in categories])


# ── Uploaded attachments ──────────────────────────────────────────────────
@public_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
