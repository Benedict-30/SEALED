import os
import io
from django.http import FileResponse
from docxtpl import DocxTemplate
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
    CustomUser, Barangay, DocumentType, DocumentRequest, DocumentRequestItem, Notification, ActivityLog
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

def verify_document_view(request):
    code = request.GET.get('code', '').strip().upper()
    doc_request = None
    error = None
    
    if code:
        try:
            doc_request = DocumentRequest.objects.select_related('resident', 'resident__barangay').get(verification_code=code)
            if doc_request.status != 'completed':
                error = "This document exists but has not been fully processed/issued yet."
        except DocumentRequest.DoesNotExist:
            error = "Invalid verification code. This document is not recognized by the system."
    
    return render(request, 'brgy/verify.html', {
        'doc_request': doc_request,
        'query': code,
        'error': error
    })


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
        form = ResidentRegistrationForm(request.POST, request.FILES)
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
def resident_profile(request):
    user = request.user
    
    if request.method == 'POST':
        if request.POST.get('edit_mode') == 'true':
            user.first_name = request.POST.get('first_name', user.first_name)
            user.middle_name = request.POST.get('middle_name', user.middle_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            user.phone_number = request.POST.get('phone_number', user.phone_number)
            user.occupation = request.POST.get('occupation', user.occupation)
            user.address = request.POST.get('address', user.address)
            
            birth_date = request.POST.get('birth_date')
            user.birth_date = birth_date if birth_date else None

            gender = request.POST.get('gender')
            if gender:
                user.gender = gender
                
            civil_status = request.POST.get('civil_status')
            if civil_status:
                user.civil_status = civil_status

            id_type = request.POST.get('id_type')
            if id_type:
                user.id_type = id_type

            if 'profile_picture' in request.FILES:
                user.profile_picture = request.FILES['profile_picture']
            if 'id_front' in request.FILES:
                user.id_front = request.FILES['id_front']
            if 'id_back' in request.FILES:
                user.id_back = request.FILES['id_back']

            if 'id_front' in request.FILES or 'id_back' in request.FILES:
                if user.verification_status == 'rejected':
                    user.verification_status = 'pending'
                    user.rejection_reason = ''

            user.save()
            log_activity(user, 'Profile Updated', f'{user.display_name} updated their profile.', request)
            messages.success(request, 'Profile updated successfully!')
            
        return redirect('profile')

    return render(request, 'brgy/resident/profile.html')


@login_required
@role_required('resident')
def request_document(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    doc_types = DocumentType.objects.filter(barangay=user.barangay, is_active=True)
    return render(request, 'brgy/resident/request_document.html', {'doc_types': doc_types})


@login_required
@role_required('resident')
def submit_bulk_request(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    if request.method == 'POST':
        doc_ids = request.POST.getlist('document_type[]')
        purpose = request.POST.get('purpose', 'Bulk Document Request')
        contact_number = request.POST.get('contact_number', user.phone_number)

        if not doc_ids:
            messages.error(request, 'Please add at least one document to your request.')
            return redirect('request_document')

        doc_req = DocumentRequest.objects.create(
            resident=user,
            purpose=purpose,
            contact_number=contact_number,
            pickup_date=timezone.now().date()
        )

        for doc_id in doc_ids:
            doc_type = get_object_or_404(DocumentType, pk=doc_id, barangay=user.barangay)
            DocumentRequestItem.objects.create(
                request=doc_req,
                document_type=doc_type,
                quantity=1,
            )

        messages.success(request, f'Your document request has been submitted successfully! Request #: {doc_req.request_number}')
        return redirect('request_history')

    return redirect('request_document')


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

@login_required
@role_required('resident')
def cancel_request(request, pk):
    doc_req = get_object_or_404(DocumentRequest, pk=pk, resident=request.user)
    
    # Only allow cancellation if the request is still pending
    if doc_req.status == 'pending':
        # Notify staff
        if doc_req.resident.barangay:
            staff_users = CustomUser.objects.filter(role='staff', barangay=doc_req.resident.barangay, is_active=True)
            for staff in staff_users:
                Notification.objects.create(
                    user=staff,
                    title='Request Cancelled',
                    message=f'{doc_req.resident.display_name} cancelled their document request ({doc_req.request_number}).',
                    link='/staff/requests/'
                )
        
        log_activity(request.user, 'Request Cancelled', f'Resident cancelled request {doc_req.request_number}.', request)
        req_num = doc_req.request_number
        doc_req.delete()
        messages.success(request, f'Request {req_num} has been successfully cancelled.')
    else:
        messages.error(request, 'You can only cancel pending requests.')
        
    return redirect('request_history')

@login_required
@role_required('resident')
def track_request(request, pk):
    doc_req = get_object_or_404(DocumentRequest, pk=pk, resident=request.user)
    return render(request, 'brgy/resident/track_request.html', {'req': doc_req})

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
    
    doc_requests = DocumentRequest.objects.filter(resident__barangay=brgy)
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
    return render(request, 'brgy/staff/reject_residents.html', {'resident': resident, 'form': form})


@login_required
@role_required('staff')
def manage_requests(request):
    user = request.user
    brgy = user.barangay
    doc_requests = DocumentRequest.objects.filter(resident__barangay=brgy)
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if status_filter:
        doc_requests = doc_requests.filter(status=status_filter)
    if search:
        doc_requests = doc_requests.filter(
            Q(request_number__icontains=search) | Q(resident__first_name__icontains=search)
            | Q(resident__last_name__icontains=search) | Q(items__document_type__name__icontains=search)
        ).distinct()
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
    doc_request = get_object_or_404(DocumentRequest, pk=pk, resident__barangay=request.user.barangay)
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

            if new_status == 'approved' and not doc_request.approved_at:
                doc_request.approved_at = timezone.now()
            elif new_status == 'ready_for_pickup' and not doc_request.ready_at:
                doc_request.ready_at = timezone.now()
            elif new_status == 'completed' and not doc_request.completed_at:
                doc_request.completed_at = timezone.now()
            # ------------------------------------------------

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
def reject_request(request, pk):
    doc_request = get_object_or_404(DocumentRequest, pk=pk, resident__barangay=request.user.barangay)
    
    if request.method == 'POST':
        Notification.objects.create(
            user=doc_request.resident,
            title='Request Rejected',
            message=f'Your document request ({doc_request.request_number}) has been rejected by the barangay staff. Please contact the barangay hall for more details.',
            link='/resident/history/'
        )
        log_activity(request.user, 'Request Rejected & Deleted', f'Request {doc_request.request_number} was rejected and deleted.', request)
        
        request_number = doc_request.request_number
        doc_request.delete()
        
        messages.success(request, f'Request {request_number} has been rejected and deleted.')
        return redirect('manage_requests')
        
    return redirect('manage_requests')


@login_required
@role_required('staff')
def staff_reports(request):
    brgy = request.user.barangay
    doc_requests = DocumentRequest.objects.filter(resident__barangay=brgy)
    daily_stats = doc_requests.annotate(date=TruncDate('created_at')).values('date').annotate(
        count=Count('id'), completed=Count('id', filter=Q(status='completed'))
    ).order_by('-date')[:30]
    status_breakdown = doc_requests.values('status').annotate(count=Count('id'))
    
    doc_type_breakdown = DocumentRequestItem.objects.filter(
        request__resident__barangay=brgy
    ).values('document_type__name').annotate(count=Count('id')).order_by('-count')
    
    total_fees = DocumentRequestItem.objects.filter(
        request__status='completed', 
        request__resident__barangay=brgy
    ).aggregate(
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
        form = DocumentTypeForm(request.POST, request.FILES)
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
        form = DocumentTypeForm(request.POST, request.FILES)
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
        form = DocumentTypeForm(request.POST, request.FILES, instance=doc_type)
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

@login_required
@role_required('staff')
def print_document(request, req_pk, item_pk):
    doc_req = get_object_or_404(DocumentRequest, pk=req_pk, resident__barangay=request.user.barangay)
    item = get_object_or_404(DocumentRequestItem, pk=item_pk, request=doc_req)
    
    doc_type = item.document_type
    
    if not doc_type.template_file or not os.path.exists(doc_type.template_file.path):
        messages.error(request, f"No Word template uploaded for {doc_type.name}.")
        return redirect('manage_requests')
        
    doc = DocxTemplate(doc_type.template_file.path)
    
    context = {
        'resident_name': doc_req.resident.display_name,
        'resident_address': doc_req.resident.address,
        'purpose': doc_req.purpose,
        'date_today': timezone.now().strftime('%B %d, %Y'),
        'barangay_name': doc_req.resident.barangay.name if doc_req.resident.barangay else '',
        'chairman_name': doc_req.resident.barangay.chairman_name if doc_req.resident.barangay else '',
        'request_number': doc_req.request_number,
        'verification_code': doc_req.verification_code or 'N/A', 
    }
    
    doc.render(context)
    
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    
    filename = f"{doc_type.name}_{doc_req.resident.last_name}_{doc_req.request_number}.docx"
    
    response = FileResponse(
        file_stream,
        as_attachment=False,
        filename=filename
    )
    response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return response


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
        total_requests=Count('users__requests', distinct=True),
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
        form = DocumentTypeForm(request.POST, request.FILES)
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
        form = DocumentTypeForm(request.POST, request.FILES, instance=doc_type)
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