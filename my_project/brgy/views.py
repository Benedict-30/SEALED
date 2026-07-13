from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q, Sum, DecimalField
from django.db.models.functions import TruncDate, Coalesce
from django.contrib import messages
from django.core.paginator import Paginator
from functools import wraps

from .models import (
    CustomUser, Barangay, DocumentType, DocumentRequest, Notification, ActivityLog
)
from .forms import (
    CustomAuthForm, ResidentRegistrationForm, DocumentRequestForm,
    StaffCreationForm, BarangayForm, DocumentTypeForm, RejectForm, UpdateStatusForm
)


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                messages.error(request, 'You do not have permission to access that page.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def log_activity(user, action, details='', request=None):
    ip = None
    if request:
        ip = request.META.get('REMOTE_ADDR')
    ActivityLog.objects.create(user=user, action=action, details=details, ip_address=ip)


def home_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'brgy/home.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = CustomAuthForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            log_activity(user, 'User Login', f'{user.display_name} logged in.', request)
            messages.success(request, f'Welcome back, {user.display_name}!')
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = CustomAuthForm()
    return render(request, 'brgy/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = ResidentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Registration successful! Your account is pending verification by barangay staff. You can log in to check your verification status.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResidentRegistrationForm()
    return render(request, 'brgy/register.html', {'form': form})


def logout_view(request):
    if request.user.is_authenticated:
        log_activity(request.user, 'User Logout', f'{request.user.display_name} logged out.', request)
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


@login_required
def dashboard_redirect(request):
    user = request.user
    if user.role == 'admin':
        return redirect('admin_dashboard')
    elif user.role == 'staff':
        return redirect('staff_dashboard')
    else:
        return redirect('resident_dashboard')


# ═══════════════════════════════════════════════════════════════
# RESIDENT VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('resident')
def resident_dashboard(request):
    user = request.user
    if not user.is_verified_resident:
        return render(request, 'brgy/resident/dashboard.html', {
            'unverified': True,
            'rejection_reason': user.rejection_reason if user.verification_status == 'rejected' else '',
        })
    reqs = DocumentRequest.objects.filter(resident=user)
    total = reqs.count()
    pending = reqs.filter(status='pending').count()
    approved = reqs.filter(status='approved').count()
    ready = reqs.filter(status='ready_for_pickup').count()
    completed = reqs.filter(status='completed').count()
    recent = reqs[:5]
    announcements = Notification.objects.filter(user=user, is_read=False).order_by('-created_at')[:3]
    return render(request, 'brgy/resident/dashboard.html', {
        'unverified': False,
        'total': total,
        'pending': pending,
        'approved': approved,
        'ready': ready,
        'completed': completed,
        'recent_requests': recent,
        'announcements': announcements,
    })


@login_required
@role_required('resident')
def request_document(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    doc_types = DocumentType.objects.filter(barangay=user.barangay, is_active=True)

    return render(request, 'brgy/resident/request_document.html', {
        'doc_types': doc_types,
    })


@login_required
@role_required('resident')
def request_document_submit(request, pk):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    doc_type = get_object_or_404(DocumentType, pk=pk, barangay=user.barangay, is_active=True)

    if request.method == 'POST':
        purpose = request.POST.get('purpose', '').strip()
        if not purpose:
            messages.error(request, 'Please state the purpose of your request.')
        else:
            doc_req = DocumentRequest.objects.create(
                resident=user,
                document_type=doc_type,
                purpose=purpose,
            )
            messages.success(request, f'Document request submitted! Request #: {doc_req.request_number}')
            return redirect('request_history')

    return render(request, 'brgy/resident/request_document_submit.html', {
        'doc_type': doc_type,
    })


@login_required
@role_required('resident')
def request_history(request):
    user = request.user
    if not user.is_verified_resident:
        return redirect('resident_dashboard')
    reqs = DocumentRequest.objects.filter(resident=user)
    status_filter = request.GET.get('status', '')
    if status_filter:
        reqs = reqs.filter(status=status_filter)
    paginator = Paginator(reqs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/request_history.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'status_choices': DocumentRequest.Status.choices,
    })


@login_required
@role_required('resident')
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(notifications, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/notifications.html', {'page_obj': page_obj})


@login_required
def mark_notification_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    if notif.link:
        return redirect(notif.link)
    return redirect('notifications')


@login_required
def mark_all_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications')


# ═══════════════════════════════════════════════════════════════
# STAFF VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('staff')
def staff_dashboard(request):
    user = request.user
    brgy = user.barangay
    pending_verifications = CustomUser.objects.filter(role='resident', barangay=brgy, verification_status='pending').count()
    verified_residents = CustomUser.objects.filter(role='resident', barangay=brgy, verification_status='approved').count()
    doc_requests = DocumentRequest.objects.filter(document_type__barangay=brgy)
    pending_requests = doc_requests.filter(status='pending').count()
    approved_requests = doc_requests.filter(status='approved').count()
    ready_requests = doc_requests.filter(status='ready_for_pickup').count()
    completed_requests = doc_requests.filter(status='completed').count()
    total_requests = doc_requests.count()
    today = timezone.now().date()
    today_requests = doc_requests.filter(created_at__date=today).count()
    today_completed = doc_requests.filter(completed_at__date=today).count()
    pending_residents = CustomUser.objects.filter(role='resident', barangay=brgy, verification_status='pending')[:5]
    pending_doc_requests = doc_requests.filter(status='pending')[:5]
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
    brgy = user.barangay
    status_filter = request.GET.get('status', 'pending')
    search = request.GET.get('search', '')
    residents = CustomUser.objects.filter(role='resident', barangay=brgy)
    if status_filter:
        residents = residents.filter(verification_status=status_filter)
    if search:
        residents = residents.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search)
            | Q(username__icontains=search) | Q(email__icontains=search)
        )
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
    resident = get_object_or_404(CustomUser, pk=pk, role='resident', barangay=request.user.barangay)
    resident.verification_status = 'approved'
    resident.rejection_reason = ''
    resident.save()
    Notification.objects.create(
        user=resident,
        title='Account Verified',
        message='Your account has been verified. You can now request barangay documents.',
        link='/resident/',
    )
    log_activity(request.user, 'Resident Verified', f'Approved {resident.display_name}.', request)
    messages.success(request, f'{resident.display_name} has been verified.')
    return redirect('verify_residents')


@login_required
@role_required('staff')
def reject_resident(request, pk):
    resident = get_object_or_404(CustomUser, pk=pk, role='resident', barangay=request.user.barangay)
    if request.method == 'POST':
        form = RejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['reason']
            resident.verification_status = 'rejected'
            resident.rejection_reason = reason
            resident.save()
            Notification.objects.create(
                user=resident,
                title='Account Rejected',
                message=f'Your account verification was rejected. Reason: {reason}',
                link='/resident/',
            )
            log_activity(request.user, 'Resident Rejected', f'Rejected {resident.display_name}. Reason: {reason}', request)
            messages.success(request, f'{resident.display_name} has been rejected.')
            return redirect('verify_residents')
    else:
        form = RejectForm()
    return render(request, 'brgy/staff/reject_resident.html', {'resident': resident, 'form': form})


@login_required
@role_required('staff')
def manage_requests(request):
    user = request.user
    brgy = user.barangay
    doc_requests = DocumentRequest.objects.filter(document_type__barangay=brgy)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if status_filter:
        doc_requests = doc_requests.filter(status=status_filter)
    if search:
        doc_requests = doc_requests.filter(
            Q(request_number__icontains=search) | Q(resident__first_name__icontains=search)
            | Q(resident__last_name__icontains=search) | Q(document_type__name__icontains=search)
        )
    if date_from:
        doc_requests = doc_requests.filter(created_at__date__gte=date_from)
    if date_to:
        doc_requests = doc_requests.filter(created_at__date__lte=date_to)
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
    doc_request = get_object_or_404(DocumentRequest, pk=pk, document_type__barangay=request.user.barangay)
    if request.method == 'POST':
        current = doc_request.status
        choices = [(s, l) for s, l in DocumentRequest.Status.choices if s != current]
        form = UpdateStatusForm(request.POST, choices=choices)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            notes = form.cleaned_data.get('staff_notes', '')
            rejection_reason = form.cleaned_data.get('rejection_reason', '')
            doc_request.status = new_status
            doc_request.processed_by = request.user
            if notes:
                doc_request.staff_notes = notes
            if new_status == 'rejected' and rejection_reason:
                doc_request.rejection_reason = rejection_reason
            doc_request.save()
            log_activity(request.user, f'Request {new_status}', f'{doc_request.request_number} updated from {current} to {new_status}.', request)
            messages.success(request, f'Request {doc_request.request_number} updated to {doc_request.get_status_display()}.')
            return redirect('manage_requests')
    else:
        current = doc_request.status
        choices = [(s, l) for s, l in DocumentRequest.Status.choices if s != current]
        form = UpdateStatusForm(choices=choices)
    return render(request, 'brgy/staff/update_request.html', {'doc_request': doc_request, 'form': form})


@login_required
@role_required('staff')
def staff_reports(request):
    brgy = request.user.barangay
    doc_requests = DocumentRequest.objects.filter(document_type__barangay=brgy)
    daily_stats = doc_requests.annotate(date=TruncDate('created_at')).values('date').annotate(
        count=Count('id'), completed=Count('id', filter=Q(status='completed'))
    ).order_by('-date')[:30]
    status_breakdown = doc_requests.values('status').annotate(count=Count('id'))
    doc_type_breakdown = doc_requests.values('document_type__name').annotate(count=Count('id')).order_by('-count')
    total_fees = doc_requests.filter(status='completed').aggregate(
        total=Coalesce(Sum('document_type__fee'), 0, output_field=DecimalField())
    )['total']
    monthly_stats = doc_requests.annotate(month=TruncDate('created_at')).values('month').annotate(
        count=Count('id')
    ).order_by('-month')[:12]
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
    doc_types = DocumentType.objects.filter(barangay=brgy).order_by('name')
    search = request.GET.get('search', '')
    if search:
        doc_types = doc_types.filter(Q(name__icontains=search))

    if request.method == 'POST':
        form = DocumentTypeForm(request.POST)
        if form.is_valid():
            dt = form.save(commit=False)
            dt.barangay = brgy
            dt.save()
            messages.success(request, f'{dt.name} added successfully.')
            return redirect('staff_manage_document_types')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(initial={'barangay': brgy})

    paginator = Paginator(doc_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'brgy/staff/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search, 'brgy': brgy,
    })


@login_required
@role_required('staff')
def staff_create_document_type(request):
    brgy = request.user.barangay
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST)
        if form.is_valid():
            dt = form.save(commit=False)
            dt.barangay = brgy
            dt.save()
            messages.success(request, f'{dt.name} added successfully.')
            return redirect('staff_manage_document_types')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(initial={'barangay': brgy})
    return render(request, 'brgy/staff/document_type_form.html', {
        'form': form, 'title': 'Add Document Type', 'brgy': brgy,
    })


@login_required
@role_required('staff')
def staff_edit_document_type(request, pk):
    brgy = request.user.barangay
    doc_type = get_object_or_404(DocumentType, pk=pk, barangay=brgy)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, instance=doc_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('staff_manage_document_types')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type)
    return render(request, 'brgy/staff/document_type_form.html', {
        'form': form, 'title': f'Edit - {doc_type.name}', 'brgy': brgy,
    })


# ═══════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ═══════════════════════════════════════════════════════════════

@login_required
@role_required('admin')
def admin_dashboard(request):
    total_residents = CustomUser.objects.filter(role='resident').count()
    verified_residents = CustomUser.objects.filter(role='resident', verification_status='approved').count()
    total_staff = CustomUser.objects.filter(role='staff').count()
    active_staff = CustomUser.objects.filter(role='staff', is_active=True).count()
    total_barangays = Barangay.objects.filter(is_active=True).count()
    pending_verifications = CustomUser.objects.filter(role='resident', verification_status='pending').count()
    all_requests = DocumentRequest.objects.all()
    total_requests = all_requests.count()
    pending_requests = all_requests.filter(status='pending').count()
    completed_requests = all_requests.filter(status='completed').count()
    recent_logs = ActivityLog.objects.all()[:10]
    barangay_stats = Barangay.objects.filter(is_active=True).annotate(
        total_residents=Count('users', filter=Q(users__role='resident', users__verification_status='approved')),
        total_requests=Count('document_types__requests'),
    ).order_by('-total_requests')[:5]
    monthly_trend = all_requests.annotate(month=TruncDate('created_at')).values('month').annotate(
        count=Count('id')
    ).order_by('-month')[:6]
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
    staff_users = CustomUser.objects.filter(role='staff').order_by('-date_joined')
    search = request.GET.get('search', '')
    if search:
        staff_users = staff_users.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search)
            | Q(email__icontains=search) | Q(barangay__name__icontains=search)
        )
    paginator = Paginator(staff_users, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff account created successfully.')
            return redirect('manage_staff')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm()
    return render(request, 'brgy/admin/manage_staff.html', {'page_obj': page_obj, 'form': form, 'search': search})


@login_required
@role_required('admin')
def edit_staff(request, pk):
    staff = get_object_or_404(CustomUser, pk=pk, role='staff')
    if request.method == 'POST':
        form = StaffCreationForm(request.POST, instance=staff)
        if form.is_valid():
            form.save()
            messages.success(request, f'{staff.display_name} updated successfully.')
            return redirect('manage_staff')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffCreationForm(instance=staff)
    return render(request, 'brgy/admin/edit_staff.html', {'staff': staff, 'form': form})


@login_required
@role_required('admin')
def toggle_staff_active(request, pk):
    staff = get_object_or_404(CustomUser, pk=pk, role='staff')
    staff.is_active = not staff.is_active
    staff.save()
    status = 'activated' if staff.is_active else 'deactivated'
    log_activity(request.user, f'Staff {status}', f'{staff.display_name} was {status}.', request)
    messages.success(request, f'{staff.display_name} has been {status}.')
    return redirect('manage_staff')


@login_required
@role_required('admin')
def manage_barangays(request):
    barangays = Barangay.objects.all().order_by('-created_at')
    search = request.GET.get('search', '')
    if search:
        barangays = barangays.filter(Q(name__icontains=search) | Q(address__icontains=search))
    paginator = Paginator(barangays, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = BarangayForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Barangay added successfully.')
            return redirect('manage_barangays')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm()
    return render(request, 'brgy/admin/manage_barangays.html', {'page_obj': page_obj, 'form': form, 'search': search})


@login_required
@role_required('admin')
def edit_barangay(request, pk):
    barangay = get_object_or_404(Barangay, pk=pk)
    if request.method == 'POST':
        form = BarangayForm(request.POST, instance=barangay)
        if form.is_valid():
            form.save()
            messages.success(request, f'{barangay.name} updated successfully.')
            return redirect('manage_barangays')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BarangayForm(instance=barangay)
    return render(request, 'brgy/admin/edit_barangay.html', {'barangay': barangay, 'form': form})


@login_required
@role_required('admin')
def manage_document_types(request):
    doc_types = DocumentType.objects.all().order_by('-created_at')
    search = request.GET.get('search', '')
    brgy_filter = request.GET.get('barangay', '')
    if search:
        doc_types = doc_types.filter(Q(name__icontains=search))
    if brgy_filter:
        doc_types = doc_types.filter(barangay_id=brgy_filter)
    paginator = Paginator(doc_types, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Document type added successfully.')
            return redirect('manage_document_types')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm()
    barangays = Barangay.objects.filter(is_active=True)
    return render(request, 'brgy/admin/document_types.html', {
        'page_obj': page_obj, 'form': form, 'search': search,
        'brgy_filter': brgy_filter, 'barangays': barangays,
    })


@login_required
@role_required('admin')
def edit_document_type(request, pk):
    doc_type = get_object_or_404(DocumentType, pk=pk)
    if request.method == 'POST':
        form = DocumentTypeForm(request.POST, instance=doc_type)
        if form.is_valid():
            form.save()
            messages.success(request, f'{doc_type.name} updated successfully.')
            return redirect('manage_document_types')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DocumentTypeForm(instance=doc_type)
    return render(request, 'brgy/admin/edit_document_type.html', {'doc_type': doc_type, 'form': form})


@login_required
@role_required('admin')
def activity_logs(request):
    logs = ActivityLog.objects.all()
    action_filter = request.GET.get('action', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    if search:
        logs = logs.filter(
            Q(action__icontains=search) | Q(details__icontains=search)
            | Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search)
        )
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)
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