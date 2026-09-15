"""Shared multi-section CSV export builder and report aggregates.

Produces a single Excel-friendly (UTF-8 BOM) CSV containing metadata,
summary metrics, breakdown sections, and per-request detail rows.

All aggregation runs in Python from the already-fetched request list
(see AGENTS.md: no composite Firestore filters / order_by).
"""

import csv
from datetime import date, datetime, timedelta

from django.utils import timezone

from .models import DocumentRequest


STATUS_LABELS = dict(DocumentRequest.Status.choices)

STATUS_PILL_CLASSES = {
    'pending': 'pending',
    'approved': 'approved',
    'printed': 'printed',
    'ready_for_pickup': 'ready',
    'completed': 'completed',
    'rejected': 'rejected',
    'cancelled': 'cancelled',
}

DETAIL_HEADERS = [
    'Request Number', 'Date Submitted', 'Barangay', 'Resident', 'Email',
    'Documents', 'Purpose', 'Contact Number', 'Pickup Date', 'Pickup Slot',
    'Status', 'Total Fee', 'Payment', 'Payment Method', 'OR Number',
    'Paid At', 'Approved At', 'Printed At', 'Ready At', 'Verification Code',
    'Processed By', 'Staff Notes',
]


# ──────────────────────── formatting ────────────────────────

def _fmt_dt(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M')
    return str(value)


def _fmt_date(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _documents_summary(req):
    parts = []
    for item in req.items.all():
        doc_type = item.document_type
        if not doc_type:
            continue
        if item.quantity and item.quantity > 1:
            parts.append(f'{doc_type.name} x{item.quantity}')
        else:
            parts.append(doc_type.name)
    return '; '.join(parts)


# ──────────────────────── aggregates ────────────────────────

def fee_totals(doc_requests):
    total_fees = 0.0
    paid_count = 0
    for req in doc_requests:
        if req.is_paid:
            total_fees += req.total_fee
            paid_count += 1
    return round(total_fees, 2), paid_count


def completion_rate(doc_requests, completed=None, total=None):
    total = total if total is not None else len(doc_requests)
    if completed is None:
        completed = sum(1 for r in doc_requests if r.status == 'completed')
    return round(completed * 100 / total) if total else 0


def status_aggregate(doc_requests, total=None):
    counts = {}
    for req in doc_requests:
        counts[req.status] = counts.get(req.status, 0) + 1
    total = total if total is not None else len(doc_requests)
    rows = []
    for status, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        rows.append({
            'status': status,
            'count': count,
            'label': STATUS_LABELS.get(status, status.title()),
            'pill_class': STATUS_PILL_CLASSES.get(status, status),
            'pct': round(count * 100 / total, 1) if total else 0,
        })
    return rows


def doc_type_aggregate(doc_requests, total=None):
    counts = {}
    fees = {}
    for req in doc_requests:
        for item in req.items.all():
            doc_type = item.document_type
            name = doc_type.name if doc_type else 'Unknown'
            counts[name] = counts.get(name, 0) + 1
            if req.is_paid:
                fees[name] = fees.get(name, 0.0) + item.total_fee
    total = total if total is not None else len(doc_requests)
    rows = []
    for name, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        rows.append({
            'name': name,
            'count': count,
            'fees': round(fees.get(name, 0.0), 2),
            'pct': round(count * 100 / total, 1) if total else 0,
        })
    return rows


def payment_aggregate(doc_requests):
    counts = {}
    fees = {}
    for req in doc_requests:
        if not req.is_paid:
            continue
        method = req.payment_method or 'Unspecified'
        counts[method] = counts.get(method, 0) + 1
        fees[method] = fees.get(method, 0.0) + req.total_fee
    return [
        {'method': method, 'count': counts[method], 'fees': round(fees[method], 2)}
        for method in sorted(fees, key=fees.get, reverse=True)
    ]


def barangay_aggregate(doc_requests, barangays):
    rows = []
    for brgy in barangays:
        brgy_requests = [r for r in doc_requests if getattr(r, '_resident_brgy_id', None) == brgy.pk]
        if not brgy_requests:
            continue
        fees = sum(r.total_fee for r in brgy_requests if r.is_paid)
        rows.append({
            'barangay_name': brgy.name,
            'logo': brgy.logo if hasattr(brgy, 'logo') else None,
            'count': len(brgy_requests),
            'pending': sum(1 for r in brgy_requests if r.status == 'pending'),
            'completed': sum(1 for r in brgy_requests if r.status == 'completed'),
            'paid': sum(1 for r in brgy_requests if r.is_paid),
            'fees': round(fees, 2),
            'fees_fmt': f'{fees:,.2f}',
            'pct': round(len(brgy_requests) * 100 / len(doc_requests), 1) if doc_requests else 0,
        })
    rows.sort(key=lambda x: x['count'], reverse=True)
    return rows


def daily_stats(doc_requests, days=30):
    day_counts = {}
    for req in doc_requests:
        if req.created_at is None:
            continue
        day = req.created_at.date()
        entry = day_counts.setdefault(day, {'count': 0, 'completed': 0})
        entry['count'] += 1
        if req.status == 'completed':
            entry['completed'] += 1
    today = timezone.localdate()
    return [
        {'date': today - timedelta(days=i),
         'count': day_counts.get(today - timedelta(days=i), {}).get('count', 0),
         'completed': day_counts.get(today - timedelta(days=i), {}).get('completed', 0)}
        for i in range(days)
    ]


def _monthly_series(doc_requests, months, key, paid_only):
    buckets = {}
    for req in doc_requests:
        dt = getattr(req, key, None)
        if dt is None:
            continue
        if paid_only and not req.is_paid:
            continue
        month_key = (dt.year, dt.month)
        if paid_only:
            buckets[month_key] = buckets.get(month_key, 0.0) + req.total_fee
        else:
            buckets[month_key] = buckets.get(month_key, 0) + 1
    today = timezone.localdate()
    stats = []
    for i in range(months - 1, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=28 * i)).replace(day=1)
        amount = buckets.get((month_start.year, month_start.month), 0)
        series = {'month': month_start}
        if paid_only:
            series['fees'] = round(amount, 2)
        else:
            series['count'] = amount
        stats.append(series)
    return stats


def monthly_counts(doc_requests, months=12):
    return _monthly_series(doc_requests, months, key='created_at', paid_only=False)


def monthly_fees(doc_requests, months=12):
    return _monthly_series(doc_requests, months, key='paid_at', paid_only=True)


# ──────────────────────── detail rows ────────────────────────

def detail_row(req, barangay_name=''):
    resident = req.resident
    return [
        req.request_number or '',
        _fmt_dt(req.created_at),
        barangay_name,
        resident.display_name if resident else '',
        resident.email if resident else '',
        _documents_summary(req),
        req.purpose or '',
        req.contact_number or '',
        _fmt_date(req.pickup_date),
        req.get_pickup_slot_display() if req.pickup_date else '',
        req.get_status_display(),
        round(float(req.total_fee or 0), 2),
        req.get_payment_status_display(),
        req.payment_method or '',
        req.or_number or '',
        _fmt_dt(req.paid_at),
        _fmt_dt(req.approved_at),
        _fmt_dt(req.printed_at),
        _fmt_dt(req.ready_at),
        req.verification_code or '',
        req.processed_by.display_name if req.processed_by else '',
        req.staff_notes or '',
    ]


# ──────────────────────── CSV writer ────────────────────────

def write_report_csv(response, *, title, metadata, summary, breakdowns, detail_rows):
    """Write a BOM-prefixed, multi-section CSV into the HTTP response.

    metadata:    list of [label, value] rows
    summary:     list of [metric, value] rows
    breakdowns:  list of {'title', 'headers', 'rows'}
    detail_rows: rows matching DETAIL_HEADERS (header written by this function)
    """
    response.write('\ufeff')
    writer = csv.writer(response)

    writer.writerow([title])
    writer.writerow([])

    writer.writerow(['REPORT METADATA'])
    writer.writerow(['Field', 'Value'])
    for label, value in metadata:
        writer.writerow([label, value])
    writer.writerow([])

    writer.writerow(['SUMMARY'])
    writer.writerow(['Metric', 'Value'])
    for metric, value in summary:
        writer.writerow([metric, value])
    writer.writerow([])

    for section in breakdowns:
        writer.writerow([section['title']])
        writer.writerow(section['headers'])
        for row in section['rows']:
            writer.writerow(row)
        writer.writerow([])

    writer.writerow(['REQUEST DETAILS'])
    writer.writerow(DETAIL_HEADERS)
    for row in detail_rows:
        writer.writerow(row)