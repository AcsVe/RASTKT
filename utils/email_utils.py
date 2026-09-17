import time
import requests
from flask import current_app

# Simple in-memory access-token cache (per process). Avoids requesting a
# fresh token from Azure AD on every single email send.
_ms_token_cache = {'token': None, 'expires_at': 0}


def _get_ms_access_token():
    tenant_id     = current_app.config.get('MS_TENANT_ID', '')
    client_id     = current_app.config.get('MS_CLIENT_ID', '')
    client_secret = current_app.config.get('MS_CLIENT_SECRET', '')
    if not (tenant_id and client_id and client_secret):
        print('[email] MS Graph not configured: missing tenant_id/client_id/client_secret', flush=True)
        return None

    now = time.time()
    if _ms_token_cache['token'] and now < _ms_token_cache['expires_at'] - 60:
        return _ms_token_cache['token']

    try:
        r = requests.post(
            f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': 'https://graph.microsoft.com/.default',
                'grant_type': 'client_credentials',
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f'[email] MS token request failed: HTTP {r.status_code} — {r.text[:500]}', flush=True)
            return None
        data = r.json()
        token = data.get('access_token')
        if not token:
            print(f'[email] MS token response had no access_token: {r.text[:500]}', flush=True)
            return None
        _ms_token_cache['token'] = token
        _ms_token_cache['expires_at'] = now + int(data.get('expires_in', 3600))
        return token
    except Exception as e:
        print(f'[email] MS token request raised exception: {e}', flush=True)
        return None


def _send_via_graph(to_email, to_name, subject, html_body, bcc_list=None):
    token = _get_ms_access_token()
    if not token:
        return False

    sender_email = current_app.config.get('MS_SENDER_EMAIL', '')
    if not sender_email:
        print('[email] MS_SENDER_EMAIL is not set', flush=True)
        return False

    message = {
        'subject': subject,
        'body': {'contentType': 'HTML', 'content': html_body},
        'toRecipients': [{'emailAddress': {'address': to_email, 'name': to_name or to_email}}],
    }
    if bcc_list:
        unique_bcc = list({e.lower(): e for e in bcc_list if e and '@' in e}.values())
        if unique_bcc:
            message['bccRecipients'] = [{'emailAddress': {'address': e}} for e in unique_bcc[:50]]

    try:
        r = requests.post(
            f'https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'message': message, 'saveToSentItems': True},
            timeout=15,
        )
        if r.status_code not in (200, 201, 202):
            print(f'[email] Graph sendMail failed: HTTP {r.status_code} — {r.text[:500]} (sender={sender_email}, to={to_email})', flush=True)
            return False
        print(f'[email] sent successfully via Graph (to={to_email}, subject={subject[:60]})', flush=True)
        return True
    except Exception as e:
        print(f'[email] Graph sendMail raised exception: {e}', flush=True)
        return False


def _send(to_email, to_name, subject, html_body, bcc_list=None):
    """Send an email via Microsoft 365 (Graph API)."""
    ms_secret = current_app.config.get('MS_CLIENT_SECRET')
    if not ms_secret:
        print(f"[email] MS_CLIENT_SECRET is NOT set — cannot send (to={to_email})", flush=True)
        return False
    if not to_email or '@' not in to_email:
        return False
    return _send_via_graph(to_email, to_name, subject, html_body, bcc_list=bcc_list)


def _abs_logo_url():
    """Email clients need an absolute URL — /static/logo.png alone won't load."""
    logo = current_app.config.get('LOGO_URL', '')
    if not logo:
        return ''
    if logo.startswith('http://') or logo.startswith('https://'):
        return logo
    base = current_app.config.get('BASE_URL', '')
    if not base:
        return ''
    return base.rstrip('/') + logo


def _lookup_url(tracking_code):
    """Link the requester can open straight to their ticket's status/
    lookup page — no typing the tracking code in by hand."""
    base = current_app.config.get('BASE_URL', '')
    if not base or not tracking_code:
        return ''
    return f"{base.rstrip('/')}/ticket/{tracking_code}"


def _dashboard_url():
    """Link straight to the staff control panel."""
    base = current_app.config.get('BASE_URL', '')
    if not base:
        return ''
    return f"{base.rstrip('/')}/admin/"


def _link_button_html(url, label_ar, label_en, color='#247680'):
    if not url:
        return ''
    return f"""
    <div style="text-align:center;margin:14px 0">
      <a href="{url}" style="display:inline-block;background:{color};color:#fff;text-decoration:none;
         padding:9px 22px;border-radius:6px;font-weight:700;font-size:12.5px" dir="ltr">{label_ar} / {label_en}</a>
    </div>"""


def _lookup_link_html(t):
    return _link_button_html(_lookup_url(t.get('trackingCode')),
                              'متابعة التذكرة مباشرة', 'Track Ticket Directly')


def _dashboard_link_html():
    return _link_button_html(_dashboard_url(), 'فتح لوحة التحكم', 'Open Control Panel', color='#2E4E7A')


def _base_html(content_ar, content_en, color='#247680'):
    """Bilingual email shell: Arabic (RTL) section on top, English (LTR)
    section below. Uses a table with an explicit width attribute (not CSS
    max-width on a div) because Outlook desktop's Word-based rendering
    engine frequently ignores max-width/margin:auto on divs."""
    logo = _abs_logo_url()
    org_ar = current_app.config.get('ORG_AR', 'مدرسة الرائد العربي')
    org_en = current_app.config.get('ORG_EN', 'Al-Raed Al-Arabi School')
    logo_html = (f'<img src="{logo}" alt="logo" width="120" style="display:block;margin:0 auto 6px;max-width:120px;height:auto">'
                 if logo else '')

    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#eef1f2">
  <tr><td align="center" style="padding:16px 10px">
    <table role="presentation" width="480" cellpadding="0" cellspacing="0" border="0"
           style="width:480px;max-width:480px;background:#fff;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;font-family:Tajawal,Arial,sans-serif;font-size:13px">
      <tr><td style="background:{color};padding:12px 16px;text-align:center">
        {logo_html}
        <span style="color:#fff;font-size:13px;font-weight:700">{org_ar} — {org_en}</span>
      </td></tr>
      <tr><td dir="rtl" style="padding:14px 16px 6px;text-align:right">{content_ar}</td></tr>
      <tr><td style="padding:0 16px"><div style="border-top:1px dashed #ddd"></div></td></tr>
      <tr><td dir="ltr" style="padding:6px 16px 14px;text-align:left;font-family:Arial,sans-serif">{content_en}</td></tr>
      <tr><td style="background:#f5f5f5;padding:8px 16px;text-align:center;font-size:10px;color:#888">
        <div dir="rtl">هذا البريد مُرسَل تلقائياً من نظام طلبات الدعم الفني — يُرجى عدم الرد عليه</div>
        <div dir="ltr">This is an automated message from the IT support ticketing system — please do not reply</div>
      </td></tr>
    </table>
  </td></tr>
</table>"""


def _build_rows(pairs, bg):
    """Render only rows that actually have a value."""
    out = []
    for label, value in pairs:
        if value is None or value == '':
            continue
        out.append(
            f'<tr><td style="padding:6px 8px;background:{bg};font-weight:600;width:40%">{label}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid #eee">{value}</td></tr>'
        )
    return ''.join(out)


def _class_label(t):
    parts = [p for p in [t.get('category'), t.get('categoryItem')] if p]
    return ' / '.join(parts)


def _rows_ar(t, bg='#f0f7f8'):
    return _build_rows([
        ('الرقم التسلسلي', f'<strong style="color:#247680">#{t.get("serial","")}</strong>'),
        ('رقم الاستعلام', f'<strong dir="ltr" style="color:#247680">{t.get("trackingCode","")}</strong>'),
        ('مقدّم الطلب', t.get('teacherName')),
        ('التصنيف', _class_label(t)),
        ('الموضوع', t.get('subject')),
        ('الموقع', t.get('location')),
        ('الحالة', t.get('statusLabelAr')),
    ], bg)


def _rows_en(t, bg='#f0f7f8'):
    return _build_rows([
        ('Serial Number', f'<strong style="color:#247680">#{t.get("serial","")}</strong>'),
        ('Tracking Code', f'<strong dir="ltr" style="color:#247680">{t.get("trackingCode","")}</strong>'),
        ('Requested by', t.get('teacherName')),
        ('Category', _class_label(t)),
        ('Subject', t.get('subject')),
        ('Location', t.get('location')),
        ('Status', t.get('statusLabelEn')),
    ], bg)


def send_ticket_confirmation(t):
    """Sent to the requester right after submission. Carries BOTH numbers:
    the random tracking code (for their own lookup) and the sequential
    serial number (so it also matches what staff see on the control
    panel)."""
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">✅ تم استلام طلب الدعم الفني</h2>
    <p>شكراً <strong>{t['teacherName']}</strong>، تم تسجيل تذكرتك وهي الآن قيد المتابعة.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t)}</table>
    <p style="color:#555">احتفظ برقم الاستعلام <strong dir="ltr">{t['trackingCode']}</strong> لمتابعة حالة التذكرة والتواصل معنا بخصوصها.</p>
    {_lookup_link_html(t)}
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">✅ Support Ticket Received</h2>
    <p>Thank you <strong>{t['teacherName']}</strong>, your ticket has been logged and is now being tracked.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t)}</table>
    <p style="color:#555">Keep your tracking code <strong dir="ltr">{t['trackingCode']}</strong> to follow up on the ticket or add comments.</p>
    """
    return _send(t['teacherEmail'], t['teacherName'],
                 f"[دعم فني/IT Support] تم استلام التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en))


def send_ticket_assigned(t):
    """Sent to the staff member a ticket was (re)assigned to."""
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">📌 تم تعيين تذكرة لك</h2>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t)}</table>
    <p style="color:#555">يرجى فتح التذكرة من لوحة التحكم لمتابعتها.</p>
    {_dashboard_link_html()}
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">📌 A Ticket Was Assigned to You</h2>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t)}</table>
    <p style="color:#555">Please open the ticket from the control panel to follow up.</p>
    """
    return _send(t.get('assigneeEmail', ''), t.get('assigneeName', ''),
                 f"[دعم فني/IT Support] تم تعيين التذكرة #{t['serial']} لك",
                 _base_html(content_ar, content_en))


def send_ticket_closed(t):
    content_ar = f"""
    <h2 style="color:#27ae60;margin-top:0">✅ تم إغلاق التذكرة</h2>
    <p>عزيزي/عزيزتي <strong>{t['teacherName']}</strong>، تم إغلاق تذكرة الدعم الفني الخاصة بك.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t)}</table>
    <p style="color:#555">إذا لم تُحل المشكلة بشكل كامل، يمكنك طلب إعادة فتح التذكرة عبر الرد على هذا الإشعار أو بالتواصل مع الدعم الفني.</p>
    {_lookup_link_html(t)}
    """
    content_en = f"""
    <h2 style="color:#27ae60;margin-top:0">✅ Ticket Closed</h2>
    <p>Dear <strong>{t['teacherName']}</strong>, your support ticket has been closed.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t)}</table>
    <p style="color:#555">If the issue isn't fully resolved, please contact IT support to have the ticket reopened.</p>
    """
    return _send(t['teacherEmail'], t['teacherName'],
                 f"[دعم فني/IT Support] تم إغلاق التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en, '#27ae60'))


def send_ticket_reopened(t):
    content_ar = f"""
    <h2 style="color:#e67e22;margin-top:0">🔄 تم إعادة فتح التذكرة</h2>
    <p>عزيزي/عزيزتي <strong>{t['teacherName']}</strong>، تم إعادة فتح تذكرة الدعم الفني الخاصة بك وهي الآن قيد المتابعة مجدداً.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t, bg='#fef9f0')}</table>
    {_lookup_link_html(t)}
    """
    content_en = f"""
    <h2 style="color:#e67e22;margin-top:0">🔄 Ticket Reopened</h2>
    <p>Dear <strong>{t['teacherName']}</strong>, your support ticket has been reopened and is being followed up on again.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t, bg='#fef9f0')}</table>
    """
    return _send(t['teacherEmail'], t['teacherName'],
                 f"[دعم فني/IT Support] تم إعادة فتح التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en, '#e67e22'))


def send_ticket_merged(t, kept_serial, kept_tracking_code=None):
    lookup_html = _link_button_html(_lookup_url(kept_tracking_code),
                                     'متابعة التذكرة #%s مباشرة' % kept_serial,
                                     'Track Ticket #%s Directly' % kept_serial) if kept_tracking_code else ''
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">🔗 تم دمج التذكرة</h2>
    <p>عزيزي/عزيزتي <strong>{t['teacherName']}</strong>، تم دمج تذكرتك رقم <strong>#{t['serial']}</strong> مع التذكرة رقم <strong>#{kept_serial}</strong> لأنهما تخصان نفس المشكلة. سيتم متابعة الطلب من خلال التذكرة رقم #{kept_serial}.</p>
    {lookup_html}
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">🔗 Ticket Merged</h2>
    <p>Dear <strong>{t['teacherName']}</strong>, your ticket <strong>#{t['serial']}</strong> has been merged into ticket <strong>#{kept_serial}</strong> since they concerned the same issue. Follow-up will continue under ticket #{kept_serial}.</p>
    """
    return _send(t['teacherEmail'], t['teacherName'],
                 f"[دعم فني/IT Support] تم دمج التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en))


def send_new_comment_notification(t, comment, to_email, to_name, to_teacher=None):
    """Sent to whichever side (requester or assigned staff) did NOT post
    the comment, so both stay in the loop without needing to keep the
    page open. Shows the actual name of whoever wrote the comment
    (staff member's own name, not a generic "IT Support" label), and
    links the recipient straight to where they can act on it: the
    requester gets the direct lookup link, staff get the dashboard link.
    `to_teacher` (bool) picks which link to show; if omitted it's
    inferred by comparing `to_email` against the requester's email."""
    author_ar = comment.get('authorName') or ('الدعم الفني' if comment['authorRole'] == 'staff' else t['teacherName'])
    author_en = comment.get('authorName') or ('IT Support' if comment['authorRole'] == 'staff' else t['teacherName'])
    if to_teacher is None:
        to_teacher = bool(t.get('teacherEmail')) and to_email == t.get('teacherEmail')
    link_html = _lookup_link_html(t) if to_teacher else _dashboard_link_html()
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">💬 تعليق جديد على التذكرة #{t['serial']}</h2>
    <p><strong>{author_ar}</strong> أضاف/ت التعليق التالي:</p>
    <div style="background:#f0f7f8;border-radius:8px;padding:10px 14px;margin:10px 0;white-space:pre-wrap">{comment['body']}</div>
    {link_html}
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">💬 New Comment on Ticket #{t['serial']}</h2>
    <p><strong>{author_en}</strong> added the following comment:</p>
    <div style="background:#f0f7f8;border-radius:8px;padding:10px 14px;margin:10px 0;white-space:pre-wrap">{comment['body']}</div>
    """
    return _send(to_email, to_name,
                 f"[دعم فني/IT Support] تعليق جديد على التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en))


def send_internal_note_notification(t, comment, emails):
    """Broadcast an internal (staff-only) note to the other System
    Admins/Administrators, so internal follow-up isn't visible only to
    whoever happens to have the ticket open."""
    author = comment.get('authorName') or ''
    content_ar = f"""
    <h2 style="color:#6b7c7e;margin-top:0">🔒 ملاحظة داخلية على التذكرة #{t['serial']}</h2>
    <p><strong>{author}</strong> أضاف/ت ملاحظة داخلية (غير مرئية لمقدم الطلب):</p>
    <div style="background:#f5f5f5;border-radius:8px;padding:10px 14px;margin:10px 0;white-space:pre-wrap">{comment['body']}</div>
    {_dashboard_link_html()}
    """
    content_en = f"""
    <h2 style="color:#6b7c7e;margin-top:0">🔒 Internal Note on Ticket #{t['serial']}</h2>
    <p><strong>{author}</strong> added an internal note (hidden from the requester):</p>
    <div style="background:#f5f5f5;border-radius:8px;padding:10px 14px;margin:10px 0;white-space:pre-wrap">{comment['body']}</div>
    """
    html = _base_html(content_ar, content_en, '#6b7c7e')
    subject = f"[داخلي/Internal] ملاحظة على التذكرة #{t['serial']}"
    for email in emails:
        if email and '@' in email:
            try:
                _send(email, '', subject, html)
            except Exception as e:
                print(f"[email] internal-note notification failed for {email}: {e}", flush=True)


def send_ticket_unprocessed_reminder(t, hours, to_email, to_name):
    """Auto-reminder: no comment/status change happened on this ticket
    within `hours` hours of its creation (and it isn't in the "Waiting"
    status, which is excluded on purpose). Sent to the assignee and to
    System Admins/Administrators."""
    content_ar = f"""
    <h2 style="color:#c0392b;margin-top:0">⏰ تذكير: لم تتم معالجة الطلب حتى الآن</h2>
    <p>مرّت أكثر من <strong>{hours}</strong> ساعة على إنشاء هذه التذكرة دون أي تعليق أو إجراء بخصوصها.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t)}</table>
    {_dashboard_link_html()}
    """
    content_en = f"""
    <h2 style="color:#c0392b;margin-top:0">⏰ Reminder: Request #{t['serial']} Not Yet Processed</h2>
    <p>More than <strong>{hours}</strong> hour(s) have passed since this ticket was created with no comment or action taken on it.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t)}</table>
    """
    return _send(to_email, to_name,
                 f"[تذكير/Reminder] لم تتم معالجة الطلب رقم #{t['serial']} حتى الآن",
                 _base_html(content_ar, content_en, '#c0392b'))


def send_priority_changed(t):
    """Sent to the assignee when a ticket's priority is changed."""
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">⚡ تغيّرت أولوية التذكرة</h2>
    <p>تم تغيير أولوية التذكرة <strong>#{t['serial']}</strong> إلى <strong>{t.get('priorityLabelAr','')}</strong>.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_ar(t)}</table>
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">⚡ Ticket Priority Changed</h2>
    <p>Ticket <strong>#{t['serial']}</strong>'s priority was changed to <strong>{t.get('priorityLabelEn','')}</strong>.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">{_rows_en(t)}</table>
    """
    return _send(t.get('assigneeEmail', ''), t.get('assigneeName', ''),
                 f"[دعم فني/IT Support] تغيّرت أولوية التذكرة #{t['serial']}",
                 _base_html(content_ar, content_en))


def send_staff_new_ticket_notification(t, emails):
    """Broadcast to staff (e.g. all System Admins) when a new ticket comes
    in, so someone assigns it promptly."""
    content_ar = f"""
    <h2 style="color:#247680;margin-top:0">🆕 تذكرة دعم فني جديدة</h2>
    <table style="width:100%;border-collapse:collapse;margin:12px 0">{_rows_ar(t)}</table>
    <p style="color:#555">{t.get('description','')[:300]}</p>
    """
    content_en = f"""
    <h2 style="color:#247680;margin-top:0">🆕 New IT Support Ticket</h2>
    <table style="width:100%;border-collapse:collapse;margin:12px 0">{_rows_en(t)}</table>
    <p style="color:#555">{t.get('description','')[:300]}</p>
    """
    html = _base_html(content_ar, content_en)
    subject = f"[إشعار/Notice] تذكرة جديدة #{t['serial']}"
    for email in emails:
        if email and '@' in email:
            try:
                _send(email, '', subject, html)
            except Exception as e:
                print(f"[email] staff new-ticket notification failed for {email}: {e}", flush=True)
