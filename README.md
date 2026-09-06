# SEALED — Barangay Document Request System

A barangay-scale online document request and processing system built with
**Django 6.0** (Python 3.13) on top of **Cloud Firestore** (Firebase Admin SDK)
instead of a relational database.

Residents register and get verified, request barangay documents (barangay
clearance, certificate of residency, etc.), track their requests, and receive
in-app + email notifications. Staff verify residents, process/print requests,
collect payments, schedule pickup, and publish announcements. An admin
oversees the whole system with staff/barangay/document-type management,
system-wide reports, and activity logs.

## Architecture

- **No Django ORM.** `DATABASES` uses `django.db.backends.dummy`
  (`my_project/settings.py`). All persistence lives in Cloud Firestore via
  `brgy/firestore_db.py` (collections: `barangays`, `users`, `document_types`,
  `document_requests`, `document_request_items`, `notifications`,
  `activity_logs`, `login_attempts`, `counters`, `announcements`).
- **Never run `makemigrations` or `migrate`.** `brgy/models.py` classes are
  dict-backed wrappers, not ORM models.
- Queries avoid composite Firestore indexes: single-field equality filters are
  pushed down; everything else is filtered/sorted in Python (fine at
  barangay scale).
- Auth is Firestore-backed (`brgy.auth.FirestoreBackend` +
  `brgy.middleware.FirestoreAuthMiddleware`); sessions are signed cookies.
  Passwords use Django's `make_password`/`check_password`.
- Generated documents use `docxtpl` with `.docx` templates uploaded per
  document type under `media/document_templates/`.

## Setup

```powershell
cd my_project
python -m venv ..\venv
..\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Place the Firebase service account at `my_project/firebase_credentials.json`.
If it is missing, `settings.py` falls back to Application Default Credentials
or `FIRESTORE_EMULATOR_HOST`.

## Commands (run from `my_project/`)

- Smoke check (no Firestore needed): `..\venv\Scripts\python.exe manage.py check`
- Dev server: `..\venv\Scripts\python.exe manage.py runserver`
- Seed all roles (admin/staff/resident/resident_pending + a test barangay and
  document types; default password `Test@123`):
  `..\venv\Scripts\python.exe manage.py seed_test_users`
- Offline smoke tests (no DB/Firestore):
  `..\venv\Scripts\python.exe smoke_tests.py`

## Features

- **Auth & security** — registration, verification workflow (pending/approved/
  rejected), forgot-password email flow (timestamped, single-use tokens),
  resident change-password, brute-force login lockout, email alerts on status
  changes and verification decisions, resident deactivation/reactivation.
- **Document requests** — multi-item request cart with quantities, per-doc fee
  snapshots, request numbers `BRG-YYYYMMDD-NNNN`, print-on-demand from `.docx`
  templates, public document verification by code.
- **Tracking & statuses** — sequential workflow (pending → approved → printed
  → ready for pickup → completed, plus rejected), per-document item tracking,
  resident tracking page with progress ring, staff notes.
- **Payments** — mark paid (cash/GCash/Maya/bank transfer/other + OR number),
  paid/unpaid badges, fee totals and paid-only fee reporting.
- **Announcements** — staff publish per-barangay announcements; admins publish
  system-wide or per-barangay; residents see them on their dashboard.
- **Pickup scheduling** — residents pick a target date; staff confirm date +
  time slot when marking ready for pickup; shown to residents and staff and
  included in exports.
- **Reports & logs** — staff reports (daily/monthly stats, status & document
  breakdowns) with CSV export; admin system-wide reports (per-barangay
  breakdown, 12-month trend, CSV export); admin activity-log viewer with CSV
  export.
- **Theme** — light/dark + accent color picker (emerald green default).

## Roles

| Role | Capabilities |
| --- | --- |
| Resident | Request documents, track, cancel, change password, view announcements |
| Staff | Verify residents, process requests, print, collect payment, schedule pickup, manage document types, publish announcements, view barangay reports |
| Admin | Manage staff/barangays/document types, view activity logs & system reports, publish global announcements |

`brgy/tests.py` intentionally does not exist (no DB to test against) — use
`smoke_tests.py` and `manage.py check` for sanity verification.