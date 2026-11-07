"""خادم تجريبي لفحص المظهر: قاعدة SQLite مؤقتة ببيانات عربية أو إنجليزية، ثم تشغيل التطبيق على منفذ محلي.

python tests/audit_server.py <مجلد البيانات> <ar|en> <المنفذ>
لا يقرأ قاعدة المدرسة ولا إعداداتها؛ كل البيانات هنا مصطنعة للفحص فقط.
"""
import os
import shutil
import sys
from datetime import datetime, timedelta

DATA, LANG, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA)
os.environ.update(DATABASE_URL='sqlite:///' + os.path.join(DATA, 'tickets.db'), ADMIN_USER='admin',
                  ADMIN_PASS='audit-pass-123', SECRET_KEY='audit')
for k in ('BASE_URL', 'MS_TENANT_ID', 'MS_CLIENT_ID', 'MS_CLIENT_SECRET', 'BREVO_API_KEY'):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
app = create_app()
AR = LANG == 'ar'
T = (lambda a, e: a) if AR else (lambda a, e: e)

with app.app_context():
    from models import db, Teacher, Category, Ticket, TicketComment
    cats = Category.query.order_by(Category.id).all()
    names = [T('سامي خالد', 'Sami Khaled'), T('ليلى أحمد', 'Laila Ahmad'), T('منى سالم', 'Mona Salem')]
    teachers = []
    for i, n in enumerate(names):
        t = Teacher(name=n, email=f't{i}@school.jo', phone=f'07900000{i}', department=T('العلوم', 'Science'), active=True)
        db.session.add(t)
        teachers.append(t)
    db.session.flush()
    subjects = [T('الطابعة لا تعمل في المختبر', 'The lab printer does not work'), T('لا يوجد اتصال بالإنترنت', 'No internet connection'),
                T('شاشة العرض معطلة', 'The projector is broken'), T('طلب تثبيت برنامج', 'Software installation request')]
    for i, (st, pr) in enumerate([('open', 'high'), ('in_progress', 'medium'), ('waiting', 'low'), ('closed', 'medium'), ('open', 'low')]):
        c = cats[i % len(cats)]
        tk = Ticket(serial_number=i + 1, tracking_code=f'AUD{i:05d}', teacher_id=teachers[i % 3].id, teacher_name=names[i % 3],
                    teacher_email=f't{i % 3}@school.jo', category_id=c.id, category_name=c.name_ar if AR else (c.name_en or c.name_ar),
                    subject=subjects[i % 4], description=T('تفاصيل المشكلة كما وصفها المعلم', 'The problem as the teacher described it'),
                    location=T('المختبر 2', 'Lab 2'), priority=pr, status=st, created_at=datetime.utcnow() - timedelta(days=i),
                    closed_at=datetime.utcnow() if st == 'closed' else None)
        db.session.add(tk)
        db.session.flush()
        db.session.add(TicketComment(ticket_id=tk.id, author_role='staff', author_name=T('فني الدعم', 'Support technician'),
                                     body=T('تم استلام الطلب وسنتابعه اليوم', 'Request received; we will follow it up today')))
    db.session.commit()

from werkzeug.serving import make_server  # noqa: E402
make_server('127.0.0.1', PORT, app, threaded=True).serve_forever()
