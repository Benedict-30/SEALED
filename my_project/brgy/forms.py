import os
import secrets

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from docxtpl import DocxTemplate

from . import firestore_db
from . import template_tokens
from .models import CustomUser, DocumentType, DocumentTypeOverride, Barangay


# Allowed upload extensions grouped by purpose.  These are enforced
# server-side (the browser `accept` attribute is only a hint).
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
TEMPLATE_EXTENSIONS = {'.docx'}
REQUIREMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_TEMPLATE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_REQUIREMENT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB per file


def validate_upload(uploaded_file, allowed_extensions, max_size, field_label='file'):
    """Raise django.core.exceptions.ValidationError for disallowed files."""
    from django.core.exceptions import ValidationError

    if not uploaded_file:
        return
    ext = os.path.splitext((uploaded_file.name or '').lower())[1]
    if ext not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions))
        raise ValidationError(
            f'Invalid {field_label} type. Allowed: {allowed}.'
        )
    if uploaded_file.size and uploaded_file.size > max_size:
        raise ValidationError(
            f'{field_label.capitalize()} is too large (max {max_size // (1024 * 1024)} MB).'
        )


def detect_template_variables(source):
    """Read the Jinja2 placeholder names out of a Word (.docx) template.

    ``source`` may be a filesystem path or a file-like object (e.g. an
    uploaded file).  Returns the sorted list of variable names found in the
    document (body, headers and footers).  Raises ValidationError when the
    template cannot be parsed so the uploader gets a proper form error.
    """
    from django.core.exceptions import ValidationError

    try:
        doc = DocxTemplate(source)
        return sorted(str(v) for v in doc.get_undeclared_template_variables())
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            'This template could not be read. Make sure it is a valid .docx file.'
        ) from exc


def _detect_from_saved_template(saved_name):
    """Detect placeholders from an already-saved template (relative MEDIA name)."""
    return detect_template_variables(os.path.join(settings.MEDIA_ROOT, saved_name))


def clean_template_upload(form, upload):
    """Shared ``clean_template_file`` body for the document-template forms.

    Validates that the upload parses as a .docx template, rewinds it, and
    stashes the detected placeholder names on the form for ``save()``.
    """
    if not upload:
        form.detected_template_variables = []
        return upload
    upload.seek(0)
    form.detected_template_variables = detect_template_variables(upload)
    upload.seek(0)
    return upload


def _save_uploaded_file(uploaded_file, subdir='', allowed_extensions=None, max_size=None, field_label='file'):
    """Helper to save an uploaded file to media/storage and return its name path.

    Validates the file type and size before persisting.  Raises
    ``django.core.exceptions.ValidationError`` when the file is not allowed.
    """
    if not uploaded_file:
        return ''
    if allowed_extensions:
        validate_upload(
            uploaded_file,
            allowed_extensions,
            max_size or 5 * 1024 * 1024,
            field_label,
        )
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

    def clean(self):
        # Intentionally do NOT run AuthenticationForm.clean(), which calls
        # authenticate() internally and raises for bad credentials before the
        # view can record rate-limiting attempts.  login_view owns
        # authentication and the login lockout logic.
        return self.cleaned_data


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
    )
    id_front = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}))
    id_back = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}), required=False)
    id_selfie = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        barangays = Barangay.objects.filter(is_active=True)
        self.fields['barangay'].choices = [('', 'Select Barangay')] + [
            (b.pk if hasattr(b, 'pk') else b.get('id'), b.name if hasattr(b, 'name') else b.get('name')) 
            for b in barangays
        ]

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip()
        if not username:
            raise forms.ValidationError('Username is required.')
        existing = firestore_db.get_user_by_username(username)
        if existing:
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('Email is required.')
        for user in firestore_db.list_users(filters=[('email', '==', email)]):
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')
        if password1:
            try:
                password_validation.validate_password(password1, self)
            except forms.ValidationError as error:
                self.add_error('password1', error)
        return cleaned

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
            user.id_front = _save_uploaded_file(
                self.cleaned_data.get('id_front'), 'resident_ids',
                IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID image',
            )
        if self.cleaned_data.get('id_back'):
            user.id_back = _save_uploaded_file(
                self.cleaned_data.get('id_back'), 'resident_ids',
                IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID image',
            )
        if self.cleaned_data.get('id_selfie'):
            user.id_selfie = _save_uploaded_file(
                self.cleaned_data.get('id_selfie'), 'resident_ids',
                IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'ID selfie',
            )

        user.set_password(self.cleaned_data.get('password1'))
        user.role = 'resident'
        user.verification_status = 'pending'
        user.is_active = True
        if commit:
            user.save()
        return user


class StaffCreationForm(forms.Form):
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name', 'autocomplete': 'given-name'})
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name', 'autocomplete': 'family-name'})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email', 'autocomplete': 'email'}))
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 0917 123 4567', 'inputmode': 'tel', 'autocomplete': 'tel'}),
        required=False
    )
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password', 'autocomplete': 'new-password'}),
        required=False,
        help_text='Leave blank to keep current password.'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm Password', 'autocomplete': 'new-password'}),
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
        for name in self.errors:
            field = self.fields.get(name)
            if field:
                classes = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = f'{classes} is-invalid'.strip()
        if instance:
            for name, field in self.fields.items():
                if name == 'barangay':
                    field.initial = instance.barangay_id
                elif hasattr(instance, name):
                    field.initial = getattr(instance, name)

    def clean_username(self):
        email = (self.cleaned_data.get('email') or '')
        username = email.split('@')[0]
        if not username:
            raise forms.ValidationError('Could not derive a username from the email address.')
        existing = firestore_db.get_user_by_username(username)
        if existing:
            raise forms.ValidationError(
                'A user with this username already exists. '
                'Choose a different email or edit the staff account manually.'
            )
        return username

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('Email is required.')
        current = getattr(self.instance, 'email', None)
        for user in firestore_db.list_users(filters=[('email', '==', email)]):
            if current and user.get('email', '').lower() == current.lower() and user.get('id') == self.instance.pk:
                continue
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_phone_number(self):
        phone = (self.cleaned_data.get('phone_number') or '').strip()
        if not phone:
            return ''
        digits = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('.', '')
        if digits.startswith('+63'):
            digits = '0' + digits[3:]
        if not digits.isdigit() or len(digits) < 11:
            raise forms.ValidationError('Enter a valid phone number (e.g. 0917 123 4567).')
        return digits

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if password and password != confirm:
            self.add_error('password_confirm', 'Passwords do not match.')
        if password:
            try:
                password_validation.validate_password(password, self)
            except forms.ValidationError as error:
                self.add_error('password', error)
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
        derived_username = self.cleaned_data['email'].split('@')[0]
        user.username = derived_username
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        elif not user.pk:
            # Never fall back to a well-known default.  Generate a strong
            # random password that the admin must pass on to the staff member.
            import secrets
            password = secrets.token_urlsafe(12)
            user.set_password(password)
            user._generated_password = password
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

    def clean_theme_color(self):
        import re
        value = (self.cleaned_data.get('theme_color') or '').strip()
        if not value:
            return ''
        if not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise forms.ValidationError('Theme color must be a valid hex color like #059669.')
        return value.lower()

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
            data['logo'] = _save_uploaded_file(
                logo, 'barangay_logos', IMAGE_EXTENSIONS, MAX_IMAGE_SIZE, 'logo',
            )
        if instance and getattr(instance, 'pk', None):
            firestore_db.update_barangay(instance.pk, data)
            return instance
        barangay_id = firestore_db.create_barangay(data)
        return Barangay(data, pk=barangay_id)


SCOPE_CHOICES = [
    ('global', 'Global (all barangays)'),
    ('local', 'Specific Barangay'),
]


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
    scope = forms.ChoiceField(
        choices=SCOPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'}),
        required=False
    )
    is_active = forms.BooleanField(required=False, initial=True)
    template_file = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.docx,.doc,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'}),
        required=False,
        help_text="Upload a .docx template for this document."
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        metadata_only = kwargs.pop('metadata_only', False)
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.metadata_only = metadata_only
        if metadata_only:
            self.fields.pop('fee')
            self.fields.pop('template_file')
        else:
            self.fields.pop('scope')
            self.fields.pop('barangay')
        if 'barangay' in self.fields:
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
            if 'scope' in self.fields:
                if instance.is_global:
                    self.fields['scope'].initial = 'global'
                elif instance.barangay_id:
                    self.fields['scope'].initial = 'local'
                    self.fields['barangay'].initial = instance.barangay_id

    def clean_template_file(self):
        return clean_template_upload(self, self.cleaned_data.get('template_file'))

    def save(self, barangay_id=None, instance=None):
        instance = instance or self.instance
        cleaned = self.cleaned_data
        data = {
            'name': cleaned['name'],
            'description': cleaned.get('description', ''),
            'requirements': cleaned.get('requirements', ''),
            'is_active': cleaned.get('is_active', True),
        }
        if self.metadata_only:
            scope = cleaned.get('scope', 'local')
            data['scope'] = scope
            data['barangay_id'] = None if scope == 'global' else (barangay_id or cleaned.get('barangay'))
        else:
            data['scope'] = 'local'
            data['barangay_id'] = barangay_id or cleaned.get('barangay')
            data['fee'] = float(cleaned['fee']) if cleaned.get('fee') is not None else None
            template = cleaned.get('template_file')
            if template:
                saved_name = _save_uploaded_file(
                    template, 'document_templates',
                    TEMPLATE_EXTENSIONS, MAX_TEMPLATE_SIZE, 'document template',
                )
                data['template_file'] = saved_name
                detected = getattr(self, 'detected_template_variables', None)
                raw = (list(detected) if detected is not None
                       else _detect_from_saved_template(saved_name))
                salt = (
                    getattr(instance, 'template_salt', None)
                    or getattr(instance, 'pk', None)
                    or secrets.token_hex(4)
                )
                data['template_variables'] = template_tokens.canonicalize_variables(raw, salt)
                if not (instance and getattr(instance, 'pk', None)):
                    data['template_salt'] = salt
        if instance and getattr(instance, 'pk', None):
            firestore_db.update_document_type(instance.pk, data)
            return instance
        doc_id = firestore_db.create_document_type(data)
        return DocumentType(data, pk=doc_id)


class GlobalTypeOverrideForm(forms.Form):
    """Staff configures price/template for a global document type in their barangay."""
    fee = forms.DecimalField(
        widget=forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '0.00', 'step': '0.01'}),
        required=False,
        help_text="Leave blank to default to 0.00."
    )
    template_file = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.docx,.doc,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'}),
        required=False,
        help_text="Upload a .docx template for this document in your barangay."
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            if getattr(instance, 'fee', None) is not None:
                self.fields['fee'].initial = instance.fee

    def clean_template_file(self):
        return clean_template_upload(self, self.cleaned_data.get('template_file'))

    def _parent_template_salt(self, override, document_type_id):
        """Secret-token salt shared with the parent document type.

        Overrides reuse the parent type's salt so token sheets, uploads and
        renders all agree.  Returns '' when the parent cannot be resolved
        (token translation is then skipped; readable names still work).
        """
        parent_id = document_type_id or (
            getattr(override, 'document_type_id', None) if override else None
        )
        if not parent_id:
            return ''
        try:
            parent = DocumentType(firestore_db.get_document_type(parent_id))
        except Exception:
            return ''
        return getattr(parent, 'template_salt', '') or str(parent_id)

    def save(self, override=None, document_type_id=None, barangay_id=None):
        override = override or self.instance
        cleaned = self.cleaned_data
        data = {
            'fee': float(cleaned['fee']) if cleaned.get('fee') is not None else 0.0,
        }
        template = cleaned.get('template_file')
        if template:
            saved_name = _save_uploaded_file(
                template, 'document_templates',
                TEMPLATE_EXTENSIONS, MAX_TEMPLATE_SIZE, 'document template',
            )
            data['template_file'] = saved_name
            detected = getattr(self, 'detected_template_variables', None)
            raw = (list(detected) if detected is not None
                   else _detect_from_saved_template(saved_name))
            data['template_variables'] = template_tokens.canonicalize_variables(
                raw, self._parent_template_salt(override, document_type_id)
            )
        if override and getattr(override, 'pk', None):
            firestore_db.update_document_type_override(override.pk, data)
            return override
        data['document_type_id'] = document_type_id
        data['barangay_id'] = barangay_id
        override_id = firestore_db.create_document_type_override(data)
        return DocumentTypeOverride(data, pk=override_id)


class RejectForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input', 'placeholder': 'Provide reason for rejection...', 'rows': 4
        }),
        required=True
    )


class StaffProfileForm(forms.Form):
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email'})
    )
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone Number'}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance:
            for name, field in self.fields.items():
                if hasattr(instance, name):
                    field.initial = getattr(instance, name)


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Current Password'})
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'New Password'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm New Password'})
    )

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get('new_password')
        confirm_password = cleaned.get('confirm_password')
        if new_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        if new_password and len(new_password) < 8:
            self.add_error('new_password', 'Password must be at least 8 characters.')
        return cleaned


class RequestPasswordResetForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={'class': 'form-input', 'placeholder': 'Enter your account email'}
        )
    )


class OTPVerificationForm(forms.Form):
    otp_code = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input otp-input',
            'style': 'text-align:center;',
            'placeholder': '6-digit code',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'autocomplete': 'one-time-code',
            'maxlength': '6',
        }),
        max_length=6,
        min_length=6,
        label='One-Time PIN',
    )

    def clean_otp_code(self):
        code = (self.cleaned_data.get('otp_code') or '').strip()
        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError('Enter the 6-digit code from your email.')
        return code


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'New Password'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm New Password'})
    )

    def clean(self):
        cleaned = super().clean()
        new_password = cleaned.get('new_password')
        confirm_password = cleaned.get('confirm_password')
        if new_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        if new_password and len(new_password) < 8:
            self.add_error('new_password', 'Password must be at least 8 characters.')
        return cleaned


class MarkPaymentForm(forms.Form):
    payment_method = forms.ChoiceField(
        choices=[
            ('cash', 'Cash'),
            ('gcash', 'GCash'),
            ('maya', 'Maya'),
            ('bank_transfer', 'Bank Transfer'),
            ('other', 'Other'),
        ],
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Payment Method',
    )
    or_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'OR / Reference Number (optional)'}),
        required=False,
        label='OR / Reference Number',
        max_length=64,
    )


class AnnouncementForm(forms.Form):
    title = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Announcement title'}),
        label='Title',
        max_length=200,
    )
    body = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-input', 'placeholder': 'Write the announcement here...', 'rows': 5}),
        label='Details',
    )
    scope = forms.ChoiceField(
        choices=[('barangay', 'Specific Barangay'), ('global', 'System-Wide')],
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Scope',
        initial='barangay',
    )
    barangay = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Barangay',
        required=False,
    )
    is_published = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Publish immediately',
        required=False,
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user and self.user.role != 'admin':
            # Staff announcements are always scoped to their own barangay; the
            # template shows a static label instead of the select, so the field
            # must not be required.
            self.fields['scope'].required = False
            self.fields.pop('barangay')
        else:
            self.fields['barangay'].choices = [('', 'Select Barangay')] + [
                (b['id'], b.get('name', ''))
                for b in firestore_db.list_barangays(active_only=True, order_by='name')
            ]

    def clean_scope(self):
        scope = self.cleaned_data.get('scope')
        if self.user and self.user.role != 'admin':
            return 'barangay'
        return scope

    def clean(self):
        cleaned = super().clean()
        if self.user and self.user.role == 'admin':
            scope = cleaned.get('scope')
            barangay = cleaned.get('barangay')
            if scope == 'barangay' and not barangay:
                self.add_error('barangay', 'Please choose a barangay for this announcement.')
        return cleaned


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