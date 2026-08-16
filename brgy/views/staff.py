import io
import os
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from docxtpl import DocxTemplate

from .. import firestore_db
from ..decorators import role_required
from ..forms.admin import DocumentTypeForm
from ..forms.staff import RejectForm, UpdateStatusForm
from ..models import CustomUser, DocumentRequest, DocumentType
from ..services import (
    _delete_template_file, _doc_type_or_404, _item_or_404, _request_or_404,
    _request_search_text, _user_or_404, log_activity, notify, requests_for_barangay,
)


@login_required
@role_required('staff')
def staff_dashboard(request):
    user = request.user
    brgy = user.barangay
    all_users = firestore_db.list_users()
    residents = [
        u for u in all_users
        if u.get('role') == 'resident' and u.get('barangay_id') == brgy.pk
    ]
    pending_verifications = len([u for u in residents if u.get('verification_status') == 'pending'])
    verified_residents = len([u for u in residents if u.get('verification_status') == 'approved'])

    doc_requests = requests_for_barangay(brgy.pk)
    pending_requests = sum(1 for r in doc_requests if r.status == 'pending')
    approved_requests = sum(1 for r in doc_requests if r.status == 'approved')
    ready_requests = sum(1 for r in doc_requests if r.status == 'ready_for_pickup')
    completed_requests = sum(1 for r in doc_requests if r.status == 'completed')
    total_requests = len(doc_requests)
    today = timezone.localdate()
    today_requests = sum(1 for r in doc_requests if r.created_at.date() == today)
    today_completed = sum(1 for r in doc_requests if r.completed_at and r.completed_at.date() == today)
    pending_residents = [CustomUser(u) for u in residents if u.get('verification_status') == 'pending'][:5]
    pending_doc_requests = [r for r in doc_requests if r.status == 'pending'][:5]

    return render(request, 'brgy/staff/dashboard.html', {
        'pending_verifications': pending_verifications,
        'verified_residents': verified_residents,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'ready_requests': ready_requests,
        'completed_requests': completed_requests,
        'total_requests': total_requests,
        'today_requests': today_requests,
        'today_completed': today_completed,
        'pending_residents': pending_residents,
        'pending_doc_requests': pending_doc_requests,
    })


@login_required
@role_required('staff')
def verify_residents(request):
    user = request.user
    status_filter = request.GET.get('status', 'pending')
    search = request.GET.get('search', '')

    all_users = firestore_db.list_users(
        order_by='date_joined', descending=True,
    )
    residents = [
        CustomUser(u) for u in all_users
        if u.get('role') == 'resident' and u.get('barangay_id') == user.barangay_id
    ]
    if status_filter:
        residents = [r for r in residents if r.verification_status == status_filter]
    if search:
        search = search.lower()
        residents = [
            r for r in residents
            if search in (r.first_name or '').lower()
            or search in (r.last_name or '').lower()
            or search in (r.username or '').lower()
            or search in (r.email or '').lower()
        ]
    paginator = Paginator(residents, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/staff/verify_residents.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
    })


@login_required
@role_required('staff')
def approve_resident(request, pk):
    resident = _user_or_404(pk)
    if resident.role != 'resident' or resident.barangay_id != request.user.barangay_id:
        raise Http404
    firestore_db.update_user(resident.pk, {
        'verification_status': 'approved',
        'rejection_reason': '',
    })
    notify(
        resident.pk,
        'Account Verified',
        'Your account has been verified. You can now request barangay documents.',
        link='/resident/',
    )
    log_activity(request.user, 'Resident Verified', f'Approved {resident.display_name}.', request)
    messages.success(request, f'{resident.display_name} has been verified.')
    return redirect('verify_residents')


@login_required
@role_required('staff')
def reject_resident(request, pk):
    resident = _user_or_404(pk)
    if resident.role != 'resident' or resident.barangay_id != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        form = RejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            firestore_db.update_user(resident.pk, {
                'verification_status': 'rejected',
                'rejection_reason': reason,
            })
            notify(
                resident.pk,
                'Account Rejected',
                f'Your account verification was rejected. Reason: {reason}',
                link='/resident/',
            )
            log_activity(request.user, 'Resident Rejected',
                         f'Rejected {resident.display_name}. Reason: {reason}', request)
            messages.success(request, f'{resident.display_name} has been rejected.')
            return redirect('verify_residents')
    else:
        form = RejectForm()
    return render(request, 'brgy/staff/reject_residents.html', {'resident': resident, 'form': form})


@login_required
@role_required('staff')
def manage_requests(request):
    user = request.user
    doc_requests = requests_for_barangay(user.barangay_id)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if status_filter:
        doc_requests = [r for r in doc_requests if r.status == status_filter]
    if search:
        search = search.lower()
        doc_requests = [r for r in doc_requests if search in _request_search_text(r)]
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            doc_requests = [r for r in doc_requests if r.created_at.date() >= from_date]
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            doc_requests = [r for r in doc_requests if r.created_at.date() <= to_date]
        except ValueError:
            pass
    paginator = Paginator(doc_requests, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/staff/manage_requests.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': DocumentRequest.Status.choices,
    })


@login_required
@role_required('staff')
def update_request_status(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        current = doc_request.status
        choices = [c for c in DocumentRequest.Status.choices if c[0] != current]
        form = UpdateStatusForm(request.POST, choices=choices)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            notes = form.cleaned_data.get('staff_notes', '')
            rejection_reason = form.cleaned_data.get('rejection_reason', '')
            updates = {
                'status': new_status,
                'processed_by_id': request.user.pk,
            }
            now = firestore_db.utcnow()
            if new_status == 'approved' and not doc_request.approved_at:
                updates['approved_at'] = now
            elif new_status == 'ready_for_pickup' and not doc_request.ready_at:
                updates['ready_at'] = now
            elif new_status == 'completed' and not doc_request.completed_at:
                updates['completed_at'] = now
            if notes:
                updates['staff_notes'] = notes
            if new_status == 'rejected' and rejection_reason:
                updates['rejection_reason'] = rejection_reason
            firestore_db.update_document_request(doc_request.pk, updates)
            new_display = dict(DocumentRequest.Status.choices).get(new_status, new_status)
            log_activity(request.user, f'Request {new_status}',
                         f'{doc_request.request_number} updated from {current} to {new_status}.', request)
            # Notify the resident of the status change
            if new_status != current:
                doc_names = ', '.join(
                    item.document_type.name for item in doc_request.items.all()
                    if item.document_type
                ) or 'documents'
                status_messages = {
                    'approved': f'Your request for {doc_names} has been approved.',
                    'ready_for_pickup': f'Your document(s) [{doc_names}] is/are ready for pickup.',
                    'completed': f'Your request for {doc_names} has been completed.',
                    'rejected': f'Your request for {doc_names} has been rejected.',
                }
                notify(
                    doc_request.resident_id,
                    f'Request {new_display}',
                    status_messages.get(new_status, f'Your request status has been updated to {new_display}.'),
                    link='/resident/history/',
                )
                log_activity(request.user, f'Request Status Updated: {new_display}',
                             f'{doc_request.request_number} changed from {current} to {new_status}.', request)
            messages.success(
                request,
                f'Request {doc_request.request_number} updated to {new_display}.'
            )
            return redirect('manage_requests')
    else:
        current = doc_request.status
        choices = [c for c in DocumentRequest.Status.choices if c[0] != current]
        form = UpdateStatusForm(choices=choices)
    return render(request, 'brgy/staff/update_request.html', {'doc_request': doc_request, 'form': form})


@login_required
@role_required('staff')
def reject_request(request, pk):
    doc_request = _request_or_404(pk)
    if not doc_request.barangay or doc_request.barangay.pk != request.user.barangay_id:
        raise Http404
    if request.method == 'POST':
        reason = request.POST.get('rejection_reason', 'Rejected by barangay staff.')
        firestore_db.update_document_request(doc_request.pk, {
            'status': 'rejected',
            'rejection_reason': reason,
            'processed_by_id': request.user.pk,
        })
        notify(
            doc_request.resident_id,
            'Request Rejected',
            f'Your request for {doc_request.request_number} has been rejected. Reason: {reason}',
            link='/resident/history/',
        )
        log_activity(request.user, 'Request Rejected',
                     f'{doc_request.request_number} rejected by {request.user.display_name}.', request)
        messages.success(request, f'Request {doc_request.request_number} has been rejected.')
        return redirect('manage_requests')
    return redirect('manage_requests')


@login_required
@role_required('staff')
def staff_reports(request):
    brgy = request.user.barangay
    doc_requests = requests_for_barangay(brgy.pk)

    # Daily stats for last 30 days
    today = timezone.localdate()
    day_counts = {}
    for req in doc_requests:
        day = req.created_at.date()
        entry = day_counts.setdefault(day, {'count': 0, 'completed': 0})
        entry['count'] += 1
        if req.status == 'completed':
            entry['completed'] += 1
    daily_stats = [
        {'date': today - timedelta(days=i), 'count': day_counts.get(today - timedelta(days=i), {}).get('count', 0),
         'completed': day_counts.get(today - timedelta(days=i), {}).get('completed', 0)}
        for i in range(30)
    ]

    # Status breakdown
    status_counts = {}
    for req in doc_requests:
        status_counts[req.status] = status_counts.get(req.status, 0) + 1
    status_breakdown = [{'status': s, 'count': c} for s, c in status_counts.items()]

    # Document type breakdown
    doc_type_counts = {}
    for req in doc_requests:
        for item in req.items.all():
            name = item.document_type.name if item.document_type else 'Unknown'
            doc_type_counts[name] = doc_type_counts.get(name, 0) + 1
    doc_type_breakdown = [
        {'document_type__name': name, 'count': count}
        for name, count in sorted(doc_type_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # Total fees from completed requests
    total_fees = 0
    for req in doc_requests:
        if req.status == 'completed':
            for item in req.items.all():
                total_fees += item.total_fee

    # Monthly stats for last 12 months
    monthly_counts = {}
    for req in doc_requests:
        key = (req.created_at.year, req.created_at.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1
    monthly_stats = []
    for i in range(12):
        first = today.replace(day=1) - timedelta(days=28 * i)
        key = (first.year, first.month)
        monthly_stats.append({'month': first.replace(day=1), 'count': monthly_counts.get(key, 0)})

    return render(request, 'brgy/staff/reports.html', {
        'daily_stats': daily_stats,
        'status_breakdown': status_breakdown,
        'doc_type_breakdown': doc_type_breakdown,
        'total_fees': total_fees,
        'monthly_stats': monthly_stats,
    })


@login_required
@role_required('staff')
def staff_manage_document_types(request):
    brgy = request.user.barangay
    doc_types = firestore_db.list_document_types(
        filters=[('barangay_id', '==', brgy.pk)],
        order_by='name',
    )
    doc_types = [DocumentType(d) for d in doc_types]
    search = request.GET.get('search', '')
    if search:
        doc_types = [d for d in doc_types if search.lower() in (d.name or '').lower()]

    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES)

        if form.is_valid():
            form.save(barangay_id=brgy.pk)
            messages.success(request, f'{form.cleaned_data["name"]} added successfully.')
            return redirect('staff_manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm()

    paginator = Paginator(doc_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/staff/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search, 'brgy': brgy,
    })


@login_required
@role_required('staff')
def staff_edit_document_type(request, pk):
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if doc_type.barangay_id != brgy.pk:
        raise Http404
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES, instance=doc_type)

        if form.is_valid():
            form.save(barangay_id=brgy.pk)
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('staff_manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type)
    return render(request, 'brgy/staff/document_type_form.html', {
        'form': form, 'title': f'Edit - {doc_type.name}', 'brgy': brgy,
    })


@login_required
@role_required('staff')
def staff_delete_document_type(request, pk):
    brgy = request.user.barangay
    doc_type = _doc_type_or_404(pk)
    if doc_type.barangay_id != brgy.pk:
        raise Http404
    if request.method == 'POST':
        name = doc_type.name
        firestore_db.delete_document_type(doc_type.pk)
        _delete_template_file(doc_type)
        log_activity(request.user, 'Document Type Deleted', f'Deleted document type "{name}".', request)
        messages.success(request, f'Document type "{name}" deleted successfully.')
    else:
        messages.error(request, 'Invalid request.')
    return redirect('staff_manage_document_types')


@login_required
@role_required('staff')
def print_document(request, req_pk, item_pk):
    doc_req = _request_or_404(req_pk)
    if not doc_req.barangay or doc_req.barangay.pk != request.user.barangay_id:
        raise Http404
    item = _item_or_404(item_pk)
    if item.request_id != doc_req.pk:
        raise Http404

    doc_type = item.document_type
    if not doc_type or not doc_type.has_template:
        messages.error(request, f'No Word template uploaded for {doc_type.name if doc_type else "document"}.')
        return redirect('manage_requests')

    template_path = doc_type.template_file.path
    if not os.path.exists(template_path):
        messages.error(request, f'Template file for {doc_type.name} is missing.')
        return redirect('manage_requests')

    doc = DocxTemplate(template_path)
    context = {
        'resident_name': doc_req.resident.display_name if doc_req.resident else '',
        'resident_address': doc_req.resident.address if doc_req.resident else '',
        'purpose': doc_req.purpose,
        'date_today': timezone.now().strftime('%B %d, %Y'),
        'barangay_name': doc_req.barangay.name if doc_req.barangay else '',
        'chairman_name': doc_req.barangay.chairman_name if doc_req.barangay else '',
        'request_number': doc_req.request_number,
    }
    doc.render(context)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    resident = doc_req.resident
    filename = f"{doc_type.name}_{resident.last_name if resident else 'resident'}_{doc_req.request_number}.docx"
    response = FileResponse(
        file_stream,
        as_attachment=False,
        filename=filename,
    )
    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return response
