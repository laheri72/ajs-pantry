from flask import request, session
from flask_limiter.util import get_remote_address


JAMEA_EMAIL_DOMAIN = "@jameasaifiyah.edu"


def client_ip_key():
    return get_remote_address() or "unknown-ip"


def _endpoint_key():
    return request.endpoint or request.path or "unknown-endpoint"


def _normalize_identifier(value, append_jamea_domain=False):
    normalized = (value or "").strip().lower()
    if normalized and append_jamea_domain and "@" not in normalized:
        normalized = f"{normalized}{JAMEA_EMAIL_DOMAIN}"
    return normalized or "unknown"


def member_login_identifier_key():
    identifier = _normalize_identifier(request.form.get("email"), append_jamea_domain=True)
    return f"{_endpoint_key()}:member:{identifier}"


def staff_login_identifier_key():
    role = _normalize_identifier(request.form.get("role"))
    if role == "admin":
        identifier = _normalize_identifier(request.form.get("username"))
    else:
        identifier = _normalize_identifier(request.form.get("email"), append_jamea_domain=True)
    return f"{_endpoint_key()}:{role}:{identifier}"


def faculty_login_identifier_key():
    identifier = _normalize_identifier(request.form.get("email"), append_jamea_domain=True)
    return f"{_endpoint_key()}:faculty:{identifier}"


def platform_admin_login_identifier_key():
    identifier = _normalize_identifier(request.form.get("username"))
    return f"{_endpoint_key()}:super_admin:{identifier}"


def current_user_or_ip_key():
    user_id = session.get("user_id")
    if user_id:
        tenant_id = session.get("tenant_id") or "no-tenant"
        return f"{_endpoint_key()}:tenant:{tenant_id}:user:{user_id}"
    return f"{_endpoint_key()}:ip:{client_ip_key()}"
