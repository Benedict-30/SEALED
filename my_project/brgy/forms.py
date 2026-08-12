from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import CustomUser, DocumentRequest, DocumentType, Barangay, Notification


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


class ResidentRegistrationForm(UserCreationForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    middle_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}), required=False)
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': ''}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': ''}))
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-input'}),
        empty_label='Select Barangay'
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
    
    # ---> ADDED id_selfie FIELD HERE <---
    id_selfie = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-input', 'accept': 'image/*'}), required=False)
    
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': ''}))

    class Meta:
        model = CustomUser
        # ---> ADDED 'id_selfie' TO THE FIELDS LIST HERE <---
        fields = [
            'first_name', 'middle_name', 'last_name', 'username', 'email',
            'barangay', 'address', 'phone_number', 'birth_date', 'gender',
            'civil_status', 'occupation', 'id_type', 'id_front', 'id_back', 'id_selfie',
            'password1', 'password2'
        ]

    def clean_barangay(self):
        barangay = self.cleaned_data.get('barangay')
        if not barangay:
            raise forms.ValidationError('Please select a barangay.')
        return barangay

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'resident'
        user.verification_status = 'pending'
        user.is_active = True
        if commit:
            user.save()
        return user


class DocumentRequestForm(forms.ModelForm):
    document_type = forms.ModelChoiceField(
        queryset=DocumentType.objects.none(),
        widget=forms.Select(attrs={'class': 'form-input'}),
        empty_label='Select Document Type'
    )
    purpose = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input', 'placeholder': 'State the purpose of your request...', 'rows': 4
        })
    )

    class Meta:
        model = DocumentRequest
        fields = ['document_type', 'purpose']

    def __init__(self, resident=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if resident and resident.barangay:
            self.fields['document_type'].queryset = DocumentType.objects.filter(
                barangay=resident.barangay, is_active=True
            )


class StaffCreationForm(forms.ModelForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email'}))
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone Number'}),
        required=False
    )
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-input'}),
        empty_label='Select Barangay'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Password'}),
        help_text='Leave blank to keep current password.'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm Password'}),
        required=False
    )

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'barangay']

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirm = cleaned.get('password_confirm')
        if password and password != confirm:
            self.add_error('password_confirm', 'Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
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


class BarangayForm(forms.ModelForm):
    class Meta:
        model = Barangay
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Barangay Calicanto'}),
            'chairman_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Juan Dela Cruz'}),
            'address': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Full address'}),
            'contact_number': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 09123456789'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'e.g. brgy@email.com'}),
            'theme_color': forms.HiddenInput(),  # We control this via JS swatches
        }


class DocumentTypeForm(forms.ModelForm):
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
    barangay = forms.ModelChoiceField(
        queryset=Barangay.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-input'}),
        empty_label='Select Barangay'
    )
    
    template_file = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.docx,.doc,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'}),
        required=False,
        help_text="Upload a .docx template for this document."
    )

    class Meta:
        model = DocumentType
        fields = ['name', 'description', 'requirements', 'fee', 'barangay', 'is_active', 'template_file']


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