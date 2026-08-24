import io
import os
from datetime import datetime, date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from docxtpl import DocxTemplate

from . import firestore_db
from .auth import login_user, logout_user
from .forms import (
    CustomAuthForm, ResidentRegistrationForm, StaffCreationForm, BarangayForm,
    DocumentTypeForm, RejectForm, UpdateStatusForm,
)
from .models import (
    ActivityLog, Barangay, CustomUser, DocumentRequest, DocumentRequestItem,
    DocumentType, Notification,
    get_barangay, get_document_request, get_document_type, get_request_items,
    get_user,
)
from .forms import _save_uploaded_file


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

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
    ip = request.META.get('REMOTE_ADDR') if request else None
    firestore_db.create_activity_log({
        'user_id': user.pk if user else None,
        'action': action,
        'details': details,
        'ip_address': ip,
    })


def notify(user_id, title, message, link=''):
    firestore_db.create_notification({
        'user_id': user_id,
        'title': title,
        'message': message,
        'link': link,
        'is_read': False,
    })


def staff_of_barangay(barangay_id):
    users = firestore_db.list_users()
    return [
        u for u in users
        if u.get('role') == 'staff' and u.get('barangay_id') == barangay_id and u.get('is_active')
    ]


def requests_for_barangay(barangay_id):
    """Document requests whose resident belongs to the given barangay."""
    requests = firestore_db.list_document_requests()
    residents = {}
    for req in requests:
        resident_id = req.get('resident_id')
        if resident_id and resident_id not in residents:
            residents[resident_id] = firestore_db.get_user(resident_id)
    result = []
    for req in requests:
        resident = residents.get(req.get('resident_id'))
        if resident and resident.get('barangay_id') == barangay_id:
            result.append(DocumentRequest(req))
    return result


def _request_search_text(req):
    resident = req.resident
    parts = [req.request_number or '']
    if resident:
        parts += [resident.first_name or '', resident.last_name or '', resident.email or '']
    for item in req.items.all():
        doc_type = item.document_type
        if doc_type:
            parts.append(doc_type.name or '')
    return ' '.join(str(part) for part in parts).lower()


def _brgy_or_404(pk):
    brgy = get_barangay(pk)
    if not brgy:
        raise Http404
    return brgy


def _user_or_404(pk):
    user = get_user(pk)
    if not user:
        raise Http404
    return user


def _doc_type_or_404(pk):
    doc_type = get_document_type(pk)
    if not doc_type:
        raise Http404
    return doc_type


def _delete_template_file(doc_type):
    path = getattr(doc_type.template_file, 'path', '')
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _request_or_404(pk):
    req = get_document_request(pk)
    if not req:
        raise Http404
    return req


def _item_or_404(pk):
    item = firestore_db.get_document_request_item(pk)
    if not item:
        raise Http404
    return DocumentRequestItem(item)


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════

def home_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'brgy/home.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = CustomAuthForm()
    if request.method == 'POST':
        form = CustomAuthForm(request=request, data=request.POST)
        if form.is_valid():
            from .auth import FirestoreBackend
            user = FirestoreBackend().authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login_user(request, user)
                log_activity(user, 'User Login', f'{user.display_name} logged in.', request)
                messages.success(request, f'Welcome back, {user.display_name}!')
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    return redirect(next_url)
                return redirect('dashboard')
            form.add_error(None, 'Invalid username or password.')
    return render(request, 'brgy/login.html', {'form': form, 'page_title': 'Sign In'})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = ResidentRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            # Notify staff of the new registration
            if user.barangay_id:
                for staff in staff_of_barangay(user.barangay_id):
                    notify(
                        staff['id'],
                        'New Resident Registration',
                        f'{user.display_name} has registered and awaits verification.',
                        link='/staff/verify-residents/',
                    )
            log_activity(user, 'Resident Registration',
                         f'{user.display_name} registered an account.', request)
            messages.success(
                request,
                'Registration successful! Your account is pending verification by barangay staff. '
                'You can log in to check your verification status.'
            )
            return redirect('login')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = ResidentRegistrationForm()
    return render(request, 'brgy/register.html', {'form': form, 'page_title': 'Create Account'})


def logout_view(request):
    if request.user.is_authenticated:
        log_activity(request.user, 'User Logout', f'{request.user.display_name} logged out.', request)
    logout_user(request)
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
            'page_title': 'Resident Dashboard',
            'rejection_reason': user.rejection_reason if user.verification_status == 'rejected' else '',
        })
    reqs = firestore_db.list_document_requests(
        filters=[('resident_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )
    reqs = [DocumentRequest(r) for r in reqs]
    total = len(reqs)
    pending = sum(1 for r in reqs if r.status == 'pending')
    approved = sum(1 for r in reqs if r.status == 'approved')
    ready = sum(1 for r in reqs if r.status == 'ready_for_pickup')
    completed = sum(1 for r in reqs if r.status == 'completed')
    recent = reqs[:5]
    announcements = [
        Notification(n) for n in firestore_db.list_notifications(
            filters=[('user_id', '==', user.pk), ('is_read', '==', False)],
            order_by='created_at',
            descending=True,
            limit=3,
        )
    ]
    return render(request, 'brgy/resident/dashboard.html', {
        'unverified': False,
        'page_title': 'Resident Dashboard',
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
            updates = {
                'first_name': request.POST.get('first_name', user.first_name),
                'middle_name': request.POST.get('middle_name', user.middle_name),
                'last_name': request.POST.get('last_name', user.last_name),
                'email': request.POST.get('email', user.email),
                'phone_number': request.POST.get('phone_number', user.phone_number),
                'occupation': request.POST.get('occupation', user.occupation),
                'address': request.POST.get('address', user.address),
            }
            birth_date = request.POST.get('birth_date')
            updates['birth_date'] = None
            if birth_date:
                try:
                    updates['birth_date'] = datetime.strptime(birth_date, '%Y-%m-%d').date()
                except ValueError:
                    pass

            gender = request.POST.get('gender')
            if gender:
                updates['gender'] = gender
            civil_status = request.POST.get('civil_status')
            if civil_status:
                updates['civil_status'] = civil_status
            id_type = request.POST.get('id_type')
            if id_type:
                updates['id_type'] = id_type

            if 'profile_picture' in request.FILES:
                updates['profile_picture'] = _save_uploaded_file(
                    request.FILES['profile_picture'], 'profile_pictures'
                )
            if 'id_front' in request.FILES:
                updates['id_front'] = _save_uploaded_file(
                    request.FILES['id_front'], 'resident_ids'
                )
            if 'id_back' in request.FILES:
                updates['id_back'] = _save_uploaded_file(
                    request.FILES['id_back'], 'resident_ids'
                )

            if 'id_front' in request.FILES or 'id_back' in request.FILES:
                current = firestore_db.get_user(user.pk)
                if current and current.get('verification_status') == 'rejected':
                    updates['verification_status'] = 'pending'
                    updates['rejection_reason'] = ''

            firestore_db.update_user(user.pk, updates)
            data = firestore_db.get_user(user.pk)
            request.user = CustomUser(data)
            log_activity(request.user, 'Profile Updated',
                         f'{request.user.display_name} updated their profile.', request)
            messages.success(request, 'Profile updated successfully!')
        return redirect('profile')
    return render(request, 'brgy/resident/profile.html', {'page_title': 'My Profile'})


@login_required
@role_required('resident')
def request_document(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')
    doc_types = firestore_db.list_document_types(
        filters=[('barangay_id', '==', user.barangay_id), ('is_active', '==', True)],
        order_by='name',
    )
    doc_types = [DocumentType(d) for d in doc_types]
    return render(request, 'brgy/resident/request_document.html', {
        'doc_types': doc_types,
        'today': timezone.localdate().isoformat(),
        'page_title': 'Request Documents',
    })


@login_required
@role_required('resident')
def submit_bulk_request(request):
    user = request.user
    if not user.is_verified_resident:
        messages.warning(request, 'Your account must be verified before you can request documents.')
        return redirect('resident_dashboard')

    if request.method == 'POST':
        doc_ids = request.POST.getlist('document_type[]')
        quantities = request.POST.getlist('quantity[]')
        row_ids = request.POST.getlist('requirement_row_id[]')
        purpose = request.POST.get('purpose', 'Bulk Document Request')
        contact_number = request.POST.get('contact_number', user.phone_number)
        pickup_date = request.POST.get('pickup_date', '')

        if not doc_ids:
            messages.error(request, 'Please add at least one document to your request.')
            return redirect('request_document')

        parsed_pickup = None
        if pickup_date:
            try:
                parsed_pickup = datetime.strptime(pickup_date, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Invalid pickup date.')
                return redirect('request_document')

        items = {}
        for i, doc_id in enumerate(doc_ids):
            try:
                qty = int(quantities[i]) if i < len(quantities) else 1
            except (ValueError, TypeError):
                qty = 1
            items[doc_id] = max(1, min(qty, 20))

        request_data = {
            'resident_id': user.pk,
            'request_number': firestore_db.next_request_number(),
            'purpose': purpose,
            'contact_number': contact_number,
            'pickup_date': parsed_pickup,
            'status': 'pending',
            'staff_notes': '',
            'rejection_reason': '',
            'processed_by_id': None,
            'completed_at': None,
            'approved_at': None,
            'ready_at': None,
        }
        request_id = firestore_db.create_document_request(request_data)

        for doc_id, qty in items.items():
            doc_type = _doc_type_or_404(doc_id)
            if doc_type.barangay_id != user.barangay_id:
                raise Http404
            firestore_db.create_document_request_item({
                'request_id': request_id,
                'document_type_id': doc_type.pk,
                'quantity': qty,
            })

        request_data['id'] = request_id
        doc_req = DocumentRequest(request_data)

        # Notify staff
        if user.barangay_id:
            for staff in staff_of_barangay(user.barangay_id):
                notify(
                    staff['id'],
                    'New Document Request',
                    f'{user.display_name} submitted a new document request ({doc_req.request_number}).',
                    link='/staff/requests/',
                )
        # Notify resident
        notify(
            user.pk,
            'Request Submitted',
            f'Your document request has been submitted. Request #: {doc_req.request_number}',
            link='/resident/history/',
        )
        log_activity(user, 'Document Request Submitted',
                     f'{user.display_name} submitted document request ({doc_req.request_number})', request)

        messages.success(
            request,
            f'Your document request has been submitted successfully! Request #: {doc_req.request_number}'
        )
        return redirect('request_history')

    return redirect('request_document')


@login_required
@role_required('resident')
def request_history(request):
    user = request.user
    if not user.is_verified_resident:
        return redirect('resident_dashboard')
    reqs = firestore_db.list_document_requests(
        filters=[('resident_id', '==', user.pk)],
        order_by='created_at',
        descending=True,
    )
    reqs = [DocumentRequest(r) for r in reqs]
    status_filter = request.GET.get('status', '')
    search = request.GET.get('search', '')
    if status_filter:
        reqs = [r for r in reqs if r.status == status_filter]
    if search:
        search = search.lower()
        reqs = [r for r in reqs if search in _request_search_text(r)]
    paginator = Paginator(reqs, 10)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/request_history.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search': search,
        'status_choices': DocumentRequest.Status.choices,
        'page_title': 'Request History',
    })


@login_required
@role_required('resident')
def notifications_view(request):
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk)],
        order_by='created_at',
        descending=True,
    )
    notifications = [Notification(n) for n in notifications]
    paginator = Paginator(notifications, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'brgy/resident/notifications.html', {'page_obj': page_obj, 'page_title': 'Notifications'})


@login_required
def mark_notification_read(request, pk):
    data = firestore_db.get_notification(pk)
    if not data or data.get('user_id') != request.user.pk:
        raise Http404
    firestore_db.update_notification(pk, {'is_read': True})
    if data.get('link'):
        return redirect(data['link'])
    return redirect('notifications')


@login_required
def mark_all_notifications_read(request):
    notifications = firestore_db.list_notifications(
        filters=[('user_id', '==', request.user.pk), ('is_read', '==', False)]
    )
    for notif in notifications:
        firestore_db.update_notification(notif['id'], {'is_read': True})
    messages.success(request, 'All notifications marked as read.')
    return redirect('notifications')


@login_required
@role_required('resident')
def cancel_request(request, pk):
    doc_req = _request_or_404(pk)
    if doc_req.resident_id != request.user.pk:
        raise Http404

    if doc_req.status == 'pending':
        if doc_req.resident.barangay_id:
            for staff in staff_of_barangay(doc_req.resident.barangay_id):
                notify(
                    staff['id'],
                    'Request Cancelled',
                    f'{doc_req.resident.display_name} cancelled their document request '
                    f'({doc_req.request_number}).',
                    link='/staff/requests/',
                )
        log_activity(request.user, 'Request Cancelled',
                     f'Resident cancelled request {doc_req.request_number}.', request)
        req_num = doc_req.request_number
        for item in firestore_db.list_document_request_items(
            filters=[('request_id', '==', doc_req.pk)]
        ):
            firestore_db.delete_document_request_item(item['id'])
        firestore_db.delete_document_request(doc_req.pk)
        messages.success(request, f'Request {req_num} has been successfully cancelled.')
    else:
        messages.error(request, 'You can only cancel pending requests.')

    return redirect('request_history')


@login_required
@role_required('resident')
def track_request(request, pk):
    doc_req = _request_or_404(pk)
    if doc_req.resident_id != request.user.pk:
        raise Http404
    return render(request, 'brgy/resident/track_request.html', {'req': doc_req, 'page_title': f'Track Request - {doc_req.request_number}'})


# ═══════════════════════════════════════════════════════════════
# STAFF VIEWS
# ═══════════════════════════════════════════════════════════════

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
        'page_title': 'Staff Dashboard',
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
        'page_title': 'Verify Residents',
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
    return render(request, 'brgy/staff/reject_resident.html', {'resident': resident, 'form': form, 'page_title': 'Reject Resident'})


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
        'page_title': 'Document Requests',
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
    return render(request, 'brgy/staff/update_request.html', {'doc_request': doc_request, 'form': form, 'page_title': f'Update Request - {doc_request.request_number}'})


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
        'page_title': 'Reports',
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
        'page_title': 'Document Types',
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
        'page_title': f'Edit - {doc_type.name}',
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


# ═══════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ═══════════════════════════════════════════════════════════════

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
        'page_title': 'Admin Dashboard',
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
    return render(request, 'brgy/admin/manage_staff.html', {'page_obj': page_obj, 'form': form, 'search': search, 'page_title': 'Manage Staff'})


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
    return render(request, 'brgy/admin/edit_staff.html', {'staff': staff, 'form': form, 'page_title': f'Edit Staff - {staff.display_name}'})


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
    return render(request, 'brgy/admin/manage_barangays.html', {'page_obj': page_obj, 'form': form, 'search': search, 'page_title': 'Manage Barangays'})


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
    return render(request, 'brgy/admin/edit_barangay.html', {'barangay': barangay, 'form': form, 'page_title': 'Edit Barangay'})


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
        'page_title': 'Document Types',
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
    return render(request, 'brgy/admin/edit_document_type.html', {'doc_type': doc_type, 'form': form, 'page_title': f'Edit Document Type - {doc_type.name}'})


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
        'page_title': 'Activity Logs',
        'action_filter': action_filter,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
    })
