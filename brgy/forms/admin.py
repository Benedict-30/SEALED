from django import forms

from .. import firestore_db
from ..models import Barangay, DocumentType
from ..services import _save_uploaded_file


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
