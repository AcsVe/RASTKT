"""Real Web Push notifications — these arrive even when a staff member's
browser/PWA is completely closed. Requires a VAPID key pair (configured in
app.py) and each device's push subscription (stored via PushSubscription,
collected client-side through the Push API)."""
import json


def _do_send(app, subs, title, body, url, event_type):
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid02
    from models import db, PushSubscription

    if not subs:
        return 0

    pem = app.config.get('VAPID_PRIVATE_KEY', '')
    try:
        vapid_key = Vapid02.from_pem(pem.encode() if isinstance(pem, str) else pem)
    except Exception as e:
        print(f"[push] could not load VAPID private key: {e}", flush=True)
        return 0

    vapid_claims = {'sub': app.config.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@example.com')}
    payload_dict = {'title': title, 'body': body, 'url': url}
    if event_type:
        payload_dict['type'] = event_type
    payload = json.dumps(payload_dict)

    sent = 0
    stale_ids = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub.to_push_dict(),
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims=dict(vapid_claims),
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, 'status_code', None)
            if status in (404, 410):
                stale_ids.append(sub.id)
            else:
                print(f"[push] send failed ({status}): {e}", flush=True)
        except Exception as e:
            print(f"[push] send failed: {e}", flush=True)

    if stale_ids:
        PushSubscription.query.filter(PushSubscription.id.in_(stale_ids)).delete(synchronize_session=False)
        db.session.commit()

    print(f"[push] sent to {sent}/{len(subs)} device(s)", flush=True)
    return sent


def send_push_to_all(app, title, body, url='/admin/', event_type=None):
    """Notify every subscribed staff device (e.g. on a brand-new ticket)."""
    from models import PushSubscription
    subs = PushSubscription.query.all()
    if not subs:
        print("[push] no subscriptions registered — nothing to send", flush=True)
        return 0
    return _do_send(app, subs, title, body, url, event_type)


def send_push_to_staff(app, staff_id, title, body, url='/admin/', event_type=None):
    """Notify only one staff member's device(s) (e.g. on assignment)."""
    from models import PushSubscription
    subs = PushSubscription.query.filter_by(staff_id=staff_id).all()
    if not subs:
        return 0
    return _do_send(app, subs, title, body, url, event_type)
