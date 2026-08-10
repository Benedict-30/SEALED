from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid


class Barangay(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    address = models.TextField()
    contact_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    chairman_name = models.CharField(max_length=200, blank=True)
    officials = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    theme_color = models.CharField(
        max_length=7, 
        default='#4F46E5', 
        help_text="Hex color for barangay theme (e.g. #4F46E5)"
    )
    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def resident_count(self):
        return self.users.filter(role='resident', verification_status='approved').count()

    @property
    def staff_count(self):
        return self.users.filter(role='staff', is_active=True).count()

    @property
    def pending_requests_count(self):
        return self.document_requests.filter(status='pending').count()


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        RESIDENT = 'resident', 'Resident'
        STAFF = 'staff', 'Staff'
        ADMIN = 'admin', 'Administrator'

    class VerificationStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)
    barangay = models.ForeignKey(
        Barangay, on_delete=models.SET_NULL, null=True, blank=True, related_name='users'
    )
    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    middle_name = models.CharField(max_length=150, blank=True)
    civil_status = models.CharField(max_length=20, blank=True, default='')
    occupation = models.CharField(max_length=100, blank=True, default='')
    id_type = models.CharField(max_length=50, blank=True, default='')
    id_front = models.ImageField(upload_to='resident_ids/', blank=True, null=True)
    id_back = models.ImageField(upload_to='resident_ids/', blank=True, null=True)
    
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    rejection_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_verified_resident(self):
        return self.role == 'resident' and self.verification_status == 'approved'

    @property
    def is_pending_resident(self):
        return self.role == 'resident' and self.verification_status == 'pending'

    @property
    def display_name(self):
        return self.get_full_name() or self.username


class DocumentType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    requirements = models.TextField(blank=True, help_text="One requirement per line")
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE, related_name='document_types')
    
    template_file = models.FileField(
        upload_to='document_templates/', 
        blank=True, 
        null=True, 
        help_text="Upload a .docx template for this document"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.barangay.name}"

    @property
    def requirements_list(self):
        if not self.requirements:
            return []
        return [r.strip() for r in self.requirements.split('\n') if r.strip()]
        
    @property
    def has_template(self):
        return bool(self.template_file and self.template_file.name)


class DocumentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Ready for Pickup'
        COMPLETED = 'completed', 'Completed'
        REJECTED = 'rejected', 'Rejected'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_number = models.CharField(max_length=30, unique=True, editable=False)
    resident = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='requests')
    
    # Removed document_type from here, it is now in DocumentRequestItem
    # Added contact_number and pickup_date for the checkout form
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    pickup_date = models.DateField(null=True, blank=True)
    
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    staff_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    approved_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.request_number} - {self.resident.display_name}"

    def save(self, *args, **kwargs):
        if not self.request_number:
            today = timezone.now().strftime('%Y%m%d')
            prefix = f'BRG-{today}-'
            last = DocumentRequest.objects.filter(
                request_number__startswith=prefix
            ).order_by('request_number').last()
            if last:
                last_num = int(last.request_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.request_number = f'{prefix}{new_num:04d}'

        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def barangay(self):
        # Changed to use resident's barangay
        return self.resident.barangay if self.resident else None

    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'approved': 'info',
            'ready_for_pickup': 'success',
            'completed': 'primary',
            'rejected': 'danger',
        }
        return colors.get(self.status, 'muted')


# NEW MODEL FOR CART ITEMS
class DocumentRequestItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(DocumentRequest, related_name='items', on_delete=models.CASCADE)
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity}x {self.document_type.name}"
        
    @property
    def total_fee(self):
        return (self.document_type.fee or 0) * self.quantity


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} -> {self.user.display_name}"


class ActivityLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='logs')
    action = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Activity logs'

    def __str__(self):
        return f"{self.action} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"