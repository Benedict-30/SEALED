from django.contrib import admin
from .models import Barangay, CustomUser, DocumentType, DocumentRequest, DocumentRequestItem, Notification, ActivityLog


@admin.register(Barangay)
class BarangayAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'contact_number', 'is_active', 'created_at']
    search_fields = ['name', 'address']
    list_filter = ['is_active']


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'display_name', 'email', 'role', 'barangay', 'verification_status', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    list_filter = ['role', 'verification_status', 'is_active', 'barangay']


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'barangay', 'fee', 'is_active']
    search_fields = ['name']
    list_filter = ['barangay', 'is_active']


# NEW: Inline to show cart items inside the Document Request page
class DocumentRequestItemInline(admin.TabularInline):
    model = DocumentRequestItem
    extra = 0
    readonly_fields = ['document_type', 'quantity']


@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    # Removed 'document_type' from list_display
    list_display = ['request_number', 'resident', 'status', 'created_at']
    search_fields = ['request_number', 'resident__first_name', 'resident__last_name']
    # Removed 'document_type' from list_filter
    list_filter = ['status', 'created_at']
    
    # Attach the inline items
    inlines = [DocumentRequestItemInline]


# NEW: Register the Item model so it has its own page in Admin
@admin.register(DocumentRequestItem)
class DocumentRequestItemAdmin(admin.ModelAdmin):
    list_display = ['request', 'document_type', 'quantity']
    search_fields = ['request__request_number', 'document_type__name']
    list_filter = ['document_type']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'ip_address', 'created_at']
    search_fields = ['action', 'details']
    list_filter = ['created_at']