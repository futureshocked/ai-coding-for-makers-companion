import resend
from flask import current_app


def _resend_send(params: dict) -> str:
    resend.api_key = current_app.config["RESEND_API_KEY"]
    response = resend.Emails.send(params)
    return response["id"]


def send_tenant_approval(to_email: str, org_name: str, login_url: str) -> str:
    return _resend_send({
        "from": current_app.config["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": f"Your makerspace '{org_name}' has been approved",
        "html": (
            f"<p>Great news! Your makerspace <b>{org_name}</b> has been approved.</p>"
            f"<p>You can now log in and start managing your space:</p>"
            f"<p><a href='{login_url}'>{login_url}</a></p>"
        ),
    })


def send_tenant_rejection(to_email: str, org_name: str) -> str:
    return _resend_send({
        "from": current_app.config["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": f"Update on your makerspace application for '{org_name}'",
        "html": (
            f"<p>Thank you for applying for <b>{org_name}</b>.</p>"
            "<p>Unfortunately, your application was not approved at this time.</p>"
            "<p>If you have questions, please contact the platform administrator.</p>"
        ),
    })


def send_booking_reminder(booking, manage_url: str) -> str:
    api_key = current_app.config["RESEND_API_KEY"]
    current_app.logger.warning(
        "Resend send attempt (reminder) — key=%s…(len=%d) from=%s to=%s",
        api_key[:8] if api_key else "(empty)",
        len(api_key),
        current_app.config["RESEND_FROM_EMAIL"],
        booking.user.email,
    )
    resend.api_key = api_key
    r = booking.resource
    m = booking.user
    params = {
        "from": current_app.config["RESEND_FROM_EMAIL"],
        "to": [m.email],
        "subject": f"Reminder: {r.name} booking on {booking.starts_at:%A, %d %B %Y}",
        "html": (
            f"<p>Hi {m.display_name},</p>"
            f"<p>You have an upcoming booking:</p>"
            f"<ul>"
            f"<li><b>Resource:</b> {r.name}</li>"
            f"<li><b>Location:</b> {r.location}</li>"
            f"<li><b>Start:</b> {booking.starts_at:%A, %d %B %Y at %H:%M} UTC</li>"
            f"<li><b>End:</b> {booking.ends_at:%H:%M} UTC</li>"
            f"</ul>"
            f"<p><a href='{manage_url}'>Manage or cancel this booking</a></p>"
        ),
    }
    response = resend.Emails.send(params)
    return response["id"]


def send_password_reset(to_email: str, reset_url: str) -> str:
    api_key = current_app.config["RESEND_API_KEY"]
    current_app.logger.warning(
        "Resend send attempt (reset) — key=%s…(len=%d) from=%s to=%s",
        api_key[:8] if api_key else "(empty)",
        len(api_key),
        current_app.config["RESEND_FROM_EMAIL"],
        to_email,
    )
    resend.api_key = api_key
    params = {
        "from": current_app.config["RESEND_FROM_EMAIL"],
        "to": [to_email],
        "subject": "Reset your Makerspace password",
        "html": (
            "<p>We received a request to reset your password.</p>"
            f"<p><a href='{reset_url}'>Click here to reset your password</a></p>"
            "<p>This link expires in <b>1 hour</b>. If you didn't request a reset, "
            "you can ignore this email.</p>"
        ),
    }
    response = resend.Emails.send(params)
    return response["id"]
