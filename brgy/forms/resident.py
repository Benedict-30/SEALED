from django import forms

from ..models import Barangay, CustomUser
from ..services import _save_uploaded_file


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
