from flask import render_template, make_response, current_app
from . import main_bp

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
