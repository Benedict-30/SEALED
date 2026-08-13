import os

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from . import firestore_db
from .models import CustomUser, DocumentRequest, DocumentType, Barangay, Notification


def _save_uploaded_file(uploaded_file, subdir=''):
    """Helper to save an uploaded file to media/storage and return its name path."""
    if not uploaded_file:
        return ''
    from django.core.files.storage import default_storage
    name = os.path.join(subdir, uploaded_file.name) if subdir else uploaded_file.name
    path = default_storage.save(name, uploaded_file)
    return path


class CustomAuthForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input', 'placeholder': 'Username', 'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input', 'placeholder': 'Password', 'autocomplete': 'current-password'
        })
    )


class ResidentRegistrationForm(forms.Form):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    middle_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}), required=False)
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': ''}))
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3}))
    phone_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}), required=False)
    birth_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}), required=False)
    gender = forms.ChoiceField(
        choices=[('', 'Select Gender'), ('Male', 'Male'), ('Female', 'Female')],
        widget=forms.Select(attrs={'class': 'form-input'}),
        required=False
    )
    civil_status = forms.ChoiceField(
        choices=[('', 'Select Status'), ('Single', 'Single'), ('Married', 'Married'), ('Widowed', 'Widowed'), ('Separated', 'Separated')],
        widget=forms.Select(attrs={'class': 'form-input'}),
        required=False
    )
    occupation = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}), required=False)
    id_type = forms.ChoiceField(
        choices=[
            ('', 'Select ID Type'),
            ('National ID', 'National ID'),
            ('Driver\'s License', 'Driver\'s License'),
            ('PhilHealth ID', 'PhilHealth ID'),
            ('Voter\'s ID', 'Voter\'s ID'),
            ('Passport', 'Passport'),
            ('SSS/GSIS ID', 'SSS/GSIS ID'),
            ('Postal ID', 'Postal ID'),
            ('Senior Citizen ID', 'Senior Citizen ID'),
            ('PWD ID', 'PWD ID'),
            ('Other', 'Other'),
        ],
        widget=forms.Select(attrs={'class': 'form-input'}),
        required=False
    )
    id_front = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}), required=False)
    id_back = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}), required=False)
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        barangays = Barangay.objects.filter(is_active=True)
        self.fields['barangay'].choices = [('', 'Select Barangay')] + [
            (b.pk if hasattr(b, 'pk') else b.get('id'), b.name if hasattr(b, 'name') else b.get('name')) 
            for b in barangays
        ]

    def clean_barangay(self):
        barangay = self.cleaned_data.get('barangay')
        if not barangay:
            raise forms.ValidationError('Please select a barangay.')
        return barangay

    def save(self, commit=True):
        user = CustomUser()
        user.first_name = self.cleaned_data.get('first_name')
        user.middle_name = self.cleaned_data.get('middle_name')
        user.last_name = self.cleaned_data.get('last_name')
        user.username = self.cleaned_data.get('username')
        user.email = self.cleaned_data.get('email')
        user.barangay_id = self.cleaned_data.get('barangay')
        user.address = self.cleaned_data.get('address')
        user.phone_number = self.cleaned_data.get('phone_number')
        user.birth_date = self.cleaned_data.get('birth_date')
        user.gender = self.cleaned_data.get('gender')
        user.civil_status = self.cleaned_data.get('civil_status')
        user.occupation = self.cleaned_data.get('occupation')
        user.id_type = self.cleaned_data.get('id_type')
        
        if self.cleaned_data.get('id_front'):
            user.id_front = _save_uploaded_file(self.cleaned_data.get('id_front'))
        if self.cleaned_data.get('id_back'):
            user.id_back = _save_uploaded_file(self.cleaned_data.get('id_back'))

        user.set_password(self.cleaned_data.get('password1'))
        user.role = 'resident'
        user.verification_status = 'pending'
        user.is_active = True
        if commit:
            user.save()
        return user


class DocumentRequestForm(forms.Form):
    """Form for requesting documents using Firestore-backed models."""
    
    document_type = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Document Type'
    )
    
    quantity = forms.IntegerField(
        initial=1,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-input'})
    )
    
    purpose = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 3})
    )

    def __init__(self, resident=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if resident and resident.barangay:
            barangay_pk = resident.barangay.pk if hasattr(resident.barangay, 'pk') else resident.barangay.get('id')
            doc_types = DocumentType.objects.filter(
                barangay_id=barangay_pk, is_active=True
            )
        else:
            doc_types = DocumentType.objects.filter(is_active=True)
        self.fields['document_type'].choices = [('', 'Select Document Type')] + [
            (dt.pk if hasattr(dt, 'pk') else dt.get('id'), dt.name if hasattr(dt, 'name') else dt.get('name')) 
            for dt in doc_types
        ]


class StaffCreationForm(forms.Form):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email'}))
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone Number'}),
        required=False
    )
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password'}),
        required=False,
        help_text='Leave blank to keep current password.'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm Password'}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.instance = instance
        barangays = Barangay.objects.filter(is_active=True)
        self.fields['barangay'].choices = [('', 'Select Barangay')] + [
            (b.pk if hasattr(b, 'pk') else b.get('id'), b.name if hasattr(b, 'name') else b.get('name')) 
            for b in barangays
        ]
        if instance:
            for name, field in self.fields.items():
                if name == 'barangay':
                    field.initial = instance.barangay_id
                elif hasattr(instance, name):
                    field.initial = getattr(instance, name)

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if password and password != confirm:
            self.add_error('password_confirm', 'Passwords do not match.')
        return cleaned

    def save(self, user_instance=None, commit=True):
        user = user_instance or self.instance or CustomUser()
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data.get('phone_number')
        user.barangay_id = self.cleaned_data['barangay']
        user.role = 'staff'
        user.verification_status = 'approved'
        user.username = self.cleaned_data['email'].split('@')[0]
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_password('changeme123')
        if commit:
            user.save()
        return user


class BarangayForm(forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Barangay Calicanto'}))
    chairman_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Juan Dela Cruz'}))
    address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Full address'}))
    contact_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 09123456789'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'e.g. brgy@email.com'}))
    theme_color = forms.CharField(widget=forms.HiddenInput(), required=False)
    is_active = forms.BooleanField(required=False, initial=True)
    logo = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-input'}), required=False)

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            for name, field in self.fields.items():
                if name == 'logo':
                    continue
                if name == 'is_active':
                    field.initial = bool(instance.is_active)
                elif hasattr(instance, name):
                    field.initial = getattr(instance, name)

    def save(self, instance=None):
        instance = instance or self.instance
        data = {
            'name': self.cleaned_data['name'],
            'chairman_name': self.cleaned_data['chairman_name'],
            'address': self.cleaned_data['address'],
            'contact_number': self.cleaned_data['contact_number'],
            'email': self.cleaned_data['email'],
            'theme_color': self.cleaned_data.get('theme_color', ''),
            'is_active': self.cleaned_data.get('is_active', True),
        }
        logo = self.cleaned_data.get('logo')
        if logo:
            data['logo'] = _save_uploaded_file(logo, 'barangay_logos')
        if instance and getattr(instance, 'pk', None):
            firestore_db.update_barangay(instance.pk, data)
            return instance
        barangay_id = firestore_db.create_barangay(data)
        return Barangay(data, pk=barangay_id)


class DocumentTypeForm(forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Document Type Name'}))
    description = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Description', 'rows': 3}),
        required=False
    )
    requirements = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'One requirement per line', 'rows': 4}),
        required=False
    )
    fee = forms.DecimalField(
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0.00', 'step': '0.01'}),
        required=False
    )
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    is_active = forms.BooleanField(required=False, initial=True)
    template_file = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.docx,.doc,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'}),
        required=False,
        help_text="Upload a .docx template for this document."
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.instance = instance
        barangays = Barangay.objects.filter(is_active=True)
        self.fields['barangay'].choices = [('', 'Select Barangay')] + [
            (b.pk if hasattr(b, 'pk') else b.get('id'), b.name if hasattr(b, 'name') else b.get('name')) 
            for b in barangays
        ]
        if instance:
            for name, field in self.fields.items():
                if name in ('template_file', 'barangay'):
                    continue
                if name == 'is_active':
                    field.initial = bool(instance.is_active)
                elif hasattr(instance, name):
                    field.initial = getattr(instance, name)
            if instance.barangay_id:
                self.fields['barangay'].initial = instance.barangay_id

    def save(self, barangay_id=None, instance=None):
        instance = instance or self.instance
        cleaned = self.cleaned_data
        data = {
            'name': cleaned['name'],
            'description': cleaned.get('description', ''),
            'requirements': cleaned.get('requirements', ''),
            'fee': float(cleaned['fee']) if cleaned.get('fee') is not None else None,
            'is_active': cleaned.get('is_active', True),
            'barangay_id': barangay_id or cleaned.get('barangay'),
        }
        template = cleaned.get('template_file')
        if template:
            data['template_file'] = _save_uploaded_file(template, 'document_templates')
        if instance and getattr(instance, 'pk', None):
            firestore_db.update_document_type(instance.pk, data)
            return instance
        doc_id = firestore_db.create_document_type(data)
        return DocumentType(data, pk=doc_id)


class RejectForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input', 'placeholder': 'Provide reason for rejection...', 'rows': 4
        }),
        required=True
    )


class UpdateStatusForm(forms.Form):
    status = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-input'}))
    staff_notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Add notes (optional)', 'rows': 3}),
        required=False
    )
    rejection_reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Reason for rejection...', 'rows': 3}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop('choices', [])
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = choices