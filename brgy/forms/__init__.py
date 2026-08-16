"""Forms split by role. Re-exports everything so ``from .forms import ...`` still works."""
from ..services import _save_uploaded_file
from .admin import BarangayForm, DocumentTypeForm
from .auth import CustomAuthForm
from .resident import ResidentRegistrationForm
from .staff import RejectForm, StaffCreationForm, UpdateStatusForm

__all__ = [
    'BarangayForm', 'CustomAuthForm', 'DocumentTypeForm', 'RejectForm',
    'ResidentRegistrationForm', 'StaffCreationForm', 'UpdateStatusForm',
    '_save_uploaded_file',
]
