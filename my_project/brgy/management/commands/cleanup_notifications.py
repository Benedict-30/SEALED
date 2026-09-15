"""
Delete notifications older than the retention window (3 days).

Run manually or schedule it (e.g. daily via Windows Task Scheduler):

    python manage.py cleanup_notifications

Notification reads also trigger this lazily (debounced), so this command is
mainly for scheduled maintenance.
"""
from django.core.management.base import BaseCommand

from brgy import firestore_db


class Command(BaseCommand):
    help = f'Delete notifications older than {firestore_db.NOTIFICATION_TTL_DAYS} days.'

    def handle(self, *args, **options):
        deleted = firestore_db.delete_expired_notifications()
        self.stdout.write(self.style.SUCCESS(f'Done. Deleted {deleted} expired notification(s).'))