from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .. import firestore_db
from ..forms.auth import CustomAuthForm
from ..forms.resident import ResidentRegistrationForm
from ..services import log_activity, notify, staff_of_barangay


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
            from ..auth import FirestoreBackend
            user = FirestoreBackend().authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                from ..auth import login_user
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
    return render(request, 'brgy/login.html', {'form': form})


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
    return render(request, 'brgy/register.html', {'form': form})


def logout_view(request):
    from ..auth import logout_user
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
