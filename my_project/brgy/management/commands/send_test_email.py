"""
Send a test email through the currently configured SMTP settings.

Useful to verify the EMAIL_* values in ``.env`` before relying on OTP /
welcome emails:
    python manage.py send_test_email you@example.com
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email via the configured SMTP server.'

    def add_arguments(self, parser):
        parser.add_argument('to', type=str, help='Recipient email address.')

    def handle(self, *args, **options):
        to = (options['to'] or '').strip()
        if not to or '@' not in to:
            raise CommandError('Provide a valid recipient email address.')

        if not getattr(settings, 'EMAIL_HOST', ''):
            raise CommandError('EMAIL_HOST is not configured in .env — email sending is disabled.')

        subject = 'Barangay System — SMTP test'
        body = (
            'This is a test email from the Barangay Document System.\n'
            'If you can read this, the SMTP settings are working correctly.'
        )
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or 'no-reply@barangay.local'

        self.stdout.write(
            'Sending to %s via %s:%s (%s)...'
            % (to, settings.EMAIL_HOST, settings.EMAIL_PORT,
               'SSL' if settings.EMAIL_USE_SSL else 'TLS')
        )
        try:
            count = send_mail(subject, body, from_email, [to], fail_silently=False)
        except Exception as exc:
            raise CommandError('SMTP error: %s' % exc)
        if count:
            self.stdout.write(self.style.SUCCESS('Test email sent to %s.' % to))
        else:
            raise CommandError('send_mail reported 0 messages delivered.')