from django import forms

from ..models import Barangay, CustomUser


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
