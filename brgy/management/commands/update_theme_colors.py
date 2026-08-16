"""
Update existing barangays that still use the legacy indigo/blue default
theme (#4F46E5) to the system's emerald green default (#059669).

Usage:
    python manage.py update_theme_colors
"""
from django.core.management.base import BaseCommand

from brgy import firestore_db

GREEN = '#059669'
LEGACY_BLUE = '#4F46E5'


class Command(BaseCommand):
    help = 'Reset legacy blue (#4F46E5) barangay themes to emerald green (#059669).'

    def handle(self, *args, **options):
        updated = 0
        for barangay in firestore_db.list_barangays():
            theme = (barangay.get('theme_color') or '').strip().lower()
            if theme == LEGACY_BLUE.lower():
                firestore_db.update_barangay(barangay['id'], {'theme_color': GREEN})
                updated += 1
                self.stdout.write(f"Updated {barangay.get('name', barangay['id'])} -> {GREEN}")
        self.stdout.write(self.style.SUCCESS(f"Done. Updated {updated} barangay(s)."))
