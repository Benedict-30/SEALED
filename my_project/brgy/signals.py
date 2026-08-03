from django.db.models.signals import post_save, post_init
from django.dispatch import receiver
from django.utils import timezone
from .models import CustomUser, DocumentRequest, Notification, ActivityLog


@receiver(post_save, sender=CustomUser)
def on_user_created(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'resident':
            # Notify staff of new resident registration
            if instance.barangay:
                staff_users = CustomUser.objects.filter(
                    role='staff', barangay=instance.barangay, is_active=True
                )
                for staff in staff_users:
                    Notification.objects.create(
                        user=staff,
                        title='New Resident Registration',
                        message=f'{instance.display_name} has registered and awaits verification.',
                        link='/staff/verify-residents/'
                    )
            ActivityLog.objects.create(
                user=instance,
                action='Resident Registration',
                details=f'{instance.display_name} registered an account.'
            )
        elif instance.role == 'staff':
            ActivityLog.objects.create(
                user=None,
                action='Staff Account Created',
                details=f'Staff account created for {instance.display_name}.'
            )


# FIXED: Use values_list to avoid instantiating the model and causing recursion
@receiver(post_init, sender=DocumentRequest)
def remember_old_status(sender, instance, **kwargs):
    if instance.pk:
        # This fetches the status directly from the DB without triggering post_init again
        old_status = DocumentRequest.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        instance._old_status = old_status
    else:
        instance._old_status = None


@receiver(post_save, sender=DocumentRequest)
def on_request_created(sender, instance, created, **kwargs):
    if created:
        # Notify staff of new request
        if instance.resident.barangay:
            staff_users = CustomUser.objects.filter(
                role='staff', barangay=instance.resident.barangay, is_active=True
            )
            for staff in staff_users:
                Notification.objects.create(
                    user=staff,
                    title='New Document Request',
                    message=f'{instance.resident.display_name} submitted a new document request ({instance.request_number}).',
                    link='/staff/requests/'
                )
        # Notify resident
        Notification.objects.create(
            user=instance.resident,
            title='Request Submitted',
            message=f'Your document request has been submitted. Request #: {instance.request_number}',
            link='/resident/history/'
        )
        ActivityLog.objects.create(
            user=instance.resident,
            action='Document Request Submitted',
            details=f'{instance.resident.display_name} submitted document request ({instance.request_number})'
        )
    else:
        # Status changed
        old_status = getattr(instance, '_old_status', None)
        
        if old_status and old_status != instance.status:
            # Get all document names in this request
            doc_names = ", ".join([item.document_type.name for item in instance.items.all()])
            if not doc_names:
                doc_names = "documents"
                
            status_messages = {
                'approved': f'Your request for {doc_names} has been approved.',
                'ready_for_pickup': f'Your document(s) [{doc_names}] is/are ready for pickup.',
                'completed': f'Your request for {doc_names} has been completed.',
                'rejected': f'Your request for {doc_names} has been rejected.',
            }
            msg = status_messages.get(instance.status, f'Your request status has been updated to {instance.get_status_display()}.')

            Notification.objects.create(
                user=instance.resident,
                title=f'Request {instance.get_status_display()}',
                message=msg,
                link='/resident/history/'
            )

            ActivityLog.objects.create(
                user=instance.processed_by,
                action=f'Request Status Updated: {instance.get_status_display()}',
                details=f'{instance.request_number} changed from {old_status} to {instance.status}.'
            )