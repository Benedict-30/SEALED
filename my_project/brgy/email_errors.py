"""Human-friendly, user-safe descriptions of SMTP/email failures.

Used by the login OTP flow so the ``verify_otp`` page (and the
``send_test_email`` command) explain WHY an email couldn't be delivered instead
of showing a bare "email wasn't delivered" notice or raw server internals.
"""
import socket
import smtplib


def friendly_email_error(exc, missing_config=False):
    """Return a short, safe reason string for an email-send failure.

    ``missing_config`` is set when there is no EMAIL_HOST configured at all
    (the failure happened before any SMTP connection was attempted).
    """
    if missing_config:
        return (
            'Email sending is not configured on the server yet. '
            'An administrator needs to set the EMAIL_HOST / EMAIL_HOST_USER '
            'environment values.'
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return (
            'The email server rejected the sender\'s credentials. '
            'The app password or 2-step verification may be misconfigured.'
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return 'The email server refused the recipient address for this account.'
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return 'The email server refused or dropped the connection. Check the SMTP host and port.'
    if isinstance(exc, (socket.timeout, TimeoutError, OSError)):
        return 'The email server timed out or was unreachable. Check the SMTP host.'
    return 'Email delivery failed for an unexpected reason. Please try again later.'