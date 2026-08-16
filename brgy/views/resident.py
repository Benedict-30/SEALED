from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from .. import firestore_db
from ..decorators import role_required
from ..models import CustomUser, DocumentRequest, DocumentType, Notification
from ..services import (
    _doc_type_or_404, _request_or_404, _request_search_text, _save_uploaded_file,
    log_activity, notify, staff_of_barangay,
)


@login_required
@role_required('resident')
def resident_dashboard(request):
    user = request.user
    if not user.is_verified_resident:
        return render(request, 'brgy/resident/dashboard.html', {
            'unverified': True,
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
    return render(request, 'brgy/resident/profile.html')


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
    return render(request, 'brgy/resident/notifications.html', {'page_obj': page_obj})


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
    return render(request, 'brgy/resident/track_request.html', {'req': doc_req})
