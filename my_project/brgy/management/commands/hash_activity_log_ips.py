"""
Migrate existing activity logs so IP addresses are stored hashed.

Before this command, activity logs stored plaintext IP addresses in
``ip_address``. New logs already write ``ip_hash``. This one-off migrates
pre-existing records: it computes ``ip_hash`` from any stored ``ip_address``
and removes the plaintext value.

Usage:
    python manage.py hash_activity_log_ips
"""
from django.core.management.base import BaseCommand

from brgy import firestore_db
from brgy.security import hash_sensitive


class Command(BaseCommand):
    help = 'Hash stored plaintext IP addresses in activity logs (one-off migration).'

    def handle(self, *args, **options):
        migrated = skipped = 0
        for log in firestore_db.list_activity_logs():
            ip = log.get('ip_address')
            if ip:
                firestore_db.update_doc('activity_log', log['id'], {
                    'ip_hash': hash_sensitive(ip),
                    'ip_address': None,
                })
                migrated += 1
            elif not log.get('ip_hash'):
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(f'Done. Hashed {migrated} log(s); skipped {skipped} log(s).')
        )