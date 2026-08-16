from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from .. import firestore_db
from ..decorators import role_required
from ..forms.admin import BarangayForm, DocumentTypeForm
from ..forms.staff import StaffCreationForm
from ..models import ActivityLog, Barangay, CustomUser, DocumentRequest, DocumentType
from ..services import (
    _brgy_or_404, _delete_template_file, _doc_type_or_404, _save_uploaded_file,
    _user_or_404, log_activity,
)


@login_required
@role_required('admin')
def admin_dashboard(request):
    all_users = firestore_db.list_users()
    residents = [u for u in all_users if u.get('role') == 'resident']
    staff = [u for u in all_users if u.get('role') == 'staff']
    total_residents = len(residents)
    verified_residents = len([u for u in residents if u.get('verification_status') == 'approved'])
    total_staff = len(staff)
    active_staff = len([u for u in staff if u.get('is_active')])

    barangays = [Barangay(b) for b in firestore_db.list_barangays()]
    total_barangays = len([b for b in barangays if b.is_active])
    pending_verifications = len([u for u in residents if u.get('verification_status') == 'pending'])

    all_requests = [DocumentRequest(r) for r in firestore_db.list_document_requests()]
    total_requests = len(all_requests)
    pending_requests = sum(1 for r in all_requests if r.status == 'pending')
    completed_requests = sum(1 for r in all_requests if r.status == 'completed')

    recent_logs = [
        ActivityLog(l) for l in firestore_db.list_activity_logs(order_by='created_at', descending=True)
    ][:10]

    barangay_stats = []
    for brgy in barangays:
        if brgy.is_active:
            brgy.total_residents = len([
                u for u in residents if u.get('barangay_id') == brgy.pk
                and u.get('verification_status') == 'approved'
            ])
            brgy.total_requests = sum(1 for r in all_requests if r.barangay and r.barangay.pk == brgy.pk)
            barangay_stats.append(brgy)
    barangay_stats.sort(key=lambda b: b.total_requests, reverse=True)
    barangay_stats = barangay_stats[:5]

    monthly_counts = {}
    for req in all_requests:
        key = (req.created_at.year, req.created_at.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1
    monthly_trend = []
    today = timezone.localdate()
    for i in range(6):
        first = today.replace(day=1) - timedelta(days=28 * i)
        key = (first.year, first.month)
        monthly_trend.append({'month': first.replace(day=1), 'count': monthly_counts.get(key, 0)})

    return render(request, 'brgy/admin/dashboard.html', {
        'total_residents': total_residents,
        'verified_residents': verified_residents,
        'total_staff': total_staff,
        'active_staff': active_staff,
        'total_barangays': total_barangays,
        'pending_verifications': pending_verifications,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'completed_requests': completed_requests,
        'recent_logs': recent_logs,
        'barangay_stats': barangay_stats,
        'monthly_trend': monthly_trend,
    })


@login_required
@role_required('admin')
def manage_staff(request):
    staff_users = [
        CustomUser(u) for u in firestore_db.list_users(
            filters=[('role', '==', 'staff')],
            order_by='date_joined',
            descending=True,
        )
    ]
    search = request.GET.get('search', '')
    if search:
        search = search.lower()
        staff_users = [
            s for s in staff_users
            if search in (s.first_name or '').lower()
            or search in (s.last_name or '').lower()
            or search in (s.email or '').lower()
            or (s.barangay and search in (s.barangay.name or '').lower())
        ]
    paginator = Paginator(staff_users, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            staff = form.save()
            log_activity(request.user, 'Staff Account Created',
                         f'Staff account created for {staff.display_name}.', request)
            messages.success(request, 'Staff account created successfully.')
            return redirect('manage_staff')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm()
    return render(request, 'brgy/admin/manage_staff.html', {'page_obj': page_obj, 'form': form, 'search': search})


@login_required
@role_required('admin')
def edit_staff(request, pk):
    staff = _user_or_404(pk)
    if staff.role != 'staff':
        raise Http404
    if request.method == 'POST':
        form = StaffCreationForm(request.POST, instance=staff)
        if form.is_valid():
            form.save()
            messages.success(request, f'{staff.display_name} updated successfully.')
            return redirect('manage_staff')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm(instance=staff)
    return render(request, 'brgy/admin/edit_staff.html', {'staff': staff, 'form': form})


@login_required
@role_required('admin')
def toggle_staff_active(request, pk):
    staff = _user_or_404(pk)
    if staff.role != 'staff':
        raise Http404
    new_status = not staff.is_active
    firestore_db.update_user(staff.pk, {'is_active': new_status})
    status = 'activated' if new_status else 'deactivated'
    log_activity(request.user, f'Staff {status}', f'{staff.display_name} was {status}.', request)
    messages.success(request, f'{staff.display_name} has been {status}.')
    return redirect('manage_staff')


@login_required
@role_required('admin')
def manage_barangays(request):
    barangays = [Barangay(b) for b in firestore_db.list_barangays(order_by='created_at', descending=True)]
    search = request.GET.get('search', '')
    if search:
        search = search.lower()
        barangays = [
            b for b in barangays
            if search in (b.name or '').lower() or search in (b.address or '').lower()
        ]
    paginator = Paginator(barangays, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = BarangayForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Barangay added successfully.')
            return redirect('manage_barangays')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm()
    return render(request, 'brgy/admin/manage_barangays.html', {'page_obj': page_obj, 'form': form, 'search': search})


@login_required
@role_required('admin')
def edit_barangay(request, pk):
    barangay = _brgy_or_404(pk)
    if request.method == 'POST':
        form = BarangayForm(request.POST, request.FILES, instance=barangay)
        if form.is_valid():
            form.save()
            messages.success(request, f'{barangay.name} updated successfully.')
            return redirect('manage_barangays')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm(instance=barangay)
    return render(request, 'brgy/admin/edit_barangay.html', {'barangay': barangay, 'form': form})


@login_required
@role_required('admin')
def change_barangay_logo(request, pk):
    barangay = _brgy_or_404(pk)
    if request.method == 'POST':
        logo = request.FILES.get('logo')
        if logo:
            path = _save_uploaded_file(logo, 'barangay_logos')
            firestore_db.update_barangay(barangay.pk, {'logo': path})
            log_activity(request.user, 'Barangay Logo Updated', f'Logo updated for {barangay.name}.', request)
            messages.success(request, f'Logo for {barangay.name} updated successfully.')
        else:
            messages.error(request, 'Please select an image file to use as the logo.')
    return redirect('manage_barangays')


@login_required
@role_required('admin')
def manage_document_types(request):
    doc_types = [DocumentType(d) for d in firestore_db.list_document_types(order_by='created_at', descending=True)]
    search = request.GET.get('search', '')
    brgy_filter = request.GET.get('barangay', '')
    if search:
        doc_types = [d for d in doc_types if search.lower() in (d.name or '').lower()]
    if brgy_filter:
        doc_types = [d for d in doc_types if d.barangay_id == brgy_filter]
    paginator = Paginator(doc_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Document type added successfully.')
            return redirect('manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm()
    barangays = [Barangay(b) for b in firestore_db.list_barangays(active_only=True)]
    return render(request, 'brgy/admin/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search,
        'brgy_filter': brgy_filter, 'barangays': barangays,
    })


@login_required
@role_required('admin')
def edit_document_type(request, pk):
    doc_type = _doc_type_or_404(pk)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, request.FILES, instance=doc_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('manage_document_types')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type)
    return render(request, 'brgy/admin/edit_document_type.html', {'doc_type': doc_type, 'form': form})


@login_required
@role_required('admin')
def delete_document_type(request, pk):
    doc_type = _doc_type_or_404(pk)
    if request.method == 'POST':
        name = doc_type.name
        firestore_db.delete_document_type(doc_type.pk)
        _delete_template_file(doc_type)
        log_activity(request.user, 'Document Type Deleted', f'Deleted document type "{name}".', request)
        messages.success(request, f'Document type "{name}" deleted successfully.')
    else:
        messages.error(request, 'Invalid request.')
    return redirect('manage_document_types')


@login_required
@role_required('admin')
def activity_logs(request):
    logs = [ActivityLog(l) for l in firestore_db.list_activity_logs(order_by='created_at', descending=True)]
    action_filter = request.GET.get('action', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if action_filter:
        logs = [l for l in logs if action_filter.lower() in (l.action or '').lower()]
    if search:
        search = search.lower()
        logs = [
            l for l in logs
            if search in (l.action or '').lower()
            or search in (l.details or '').lower()
            or (l.user and (search in (l.user.first_name or '').lower()
                            or search in (l.user.last_name or '').lower()))
        ]
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            logs = [l for l in logs if l.created_at.date() >= from_date]
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            logs = [l for l in logs if l.created_at.date() <= to_date]
        except ValueError:
            pass
    paginator = Paginator(logs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/admin/activity_logs.html', {
        'page_obj': page_obj,
        'action_filter': action_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
    })
