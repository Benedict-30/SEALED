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


@receiver(post_save, sender=DocumentRequest)
def on_request_created(sender, instance, created, **kwargs):
    if created:
        # Notify staff of new request
        if instance.barangay:
            staff_users = CustomUser.objects.filter(
                role='staff', barangay=instance.barangay, is_active=True
            )
            for staff in staff_users:
                Notification.objects.create(
                    user=staff,
                    title='New Document Request',
                    message=f'{instance.resident.display_name} requested {instance.document_type.name}.',
                    link=f'/staff/requests/'
                )
        # Notify resident
        Notification.objects.create(
            user=instance.resident,
            title='Request Submitted',
            message=f'Your request for {instance.document_type.name} has been submitted. Request #: {instance.request_number}',
            link='/resident/history/'
        )
        ActivityLog.objects.create(
            user=instance.resident,
            action='Document Request Submitted',
            details=f'{instance.resident.display_name} requested {instance.document_type.name} ({instance.request_number})'
        )
    else:
        # Status changed
        old_status = None
        try:
            # Get old status from DB before save
            old_instance = DocumentRequest.objects.get(pk=instance.pk)
            old_status = old_instance.status
        except DocumentRequest.DoesNotExist:
            pass

        if old_status and old_status != instance.status:
            status_messages = {
                'approved': f'Your request for {instance.document_type.name} has been approved.',
                'ready_for_pickup': f'Your document {instance.document_type.name} is ready for pickup.',
                'completed': f'Your request for {instance.document_type.name} has been completed.',
                'rejected': f'Your request for {instance.document_type.name} has been rejected.',
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