from flask import render_template, make_response, current_app, request, jsonify, g
from . import main_bp
from app import db
from models import PushSubscription
from ..utils import _require_user, tenant_filter
import os

@main_bp.route('/service-worker.js')
def service_worker():
    response = make_response(current_app.send_static_file('service-worker.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@main_bp.route('/manifest.json')
def manifest():
    response = make_response(current_app.send_static_file('manifest.json'))
    response.headers['Content-Type'] = 'application/manifest+json'
    return response

@main_bp.route('/offline')
def offline():
    return render_template('offline.html')

@main_bp.route('/api/push/public-key')
def get_public_key():
    return jsonify({"public_key": os.environ.get("VAPID_PUBLIC_KEY")})

@main_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe_push():
    user = _require_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    
    subscription_data = request.json
    if not subscription_data:
        return jsonify({"error": "invalid_data"}), 400

    # Check if this endpoint already exists for this user
    existing = PushSubscription.query.filter_by(
        user_id=user.id, 
        endpoint=subscription_data['endpoint']
    ).first()

    if existing:
        existing.p256dh = subscription_data['keys']['p256dh']
        existing.auth = subscription_data['keys']['auth']
    else:
        new_sub = PushSubscription(
            user_id=user.id,
            endpoint=subscription_data['endpoint'],
            p256dh=subscription_data['keys']['p256dh'],
            auth=subscription_data['keys']['auth'],
            tenant_id=getattr(g, 'tenant_id', None)
        )
        db.session.add(new_sub)
    
    db.session.commit()
    return jsonify({"success": True})
