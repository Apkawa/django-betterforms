from collections import OrderedDict

from django import forms
from django.forms import formset_factory
from django.forms.models import inlineformset_factory, modelformset_factory, modelform_factory
from django.contrib.admin import widgets as admin_widgets
from django.core.exceptions import ValidationError

from betterforms.multiform import MultiFormMixin, MultiModelFormMixin, MultiModelForm

from .models import User, Profile, Badge, Author, Book, BookImage


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('name',)


class ProfileForm(forms.ModelForm):
    name = forms.CharField(label='Namespace Clash')

    class Meta:
        model = Profile
        fields = ('name', 'display_name',)


class UserProfileMultiForm(MultiModelFormMixin):
    form_classes = OrderedDict((
        ('user', UserForm),
        ('profile', ProfileForm),
    ))


class RaisesErrorForm(forms.Form):
    name = forms.CharField()
    hidden = forms.CharField(widget=forms.HiddenInput)

    class Media:
        js = ('test.js',)

    def clean(self):
        raise ValidationError('It broke')


class ErrorMultiForm(MultiFormMixin):
    form_classes = {
        'errors': RaisesErrorForm,
        'errors2': RaisesErrorForm,
    }


class FileForm(forms.Form):
    # we use this widget to test the media property
    date = forms.DateTimeField(widget=admin_widgets.AdminSplitDateTime)
    image = forms.ImageField()
    hidden = forms.CharField(widget=forms.HiddenInput)


class NeedsFileField(MultiFormMixin):
    form_classes = OrderedDict((
        ('file', FileForm),
        ('errors', RaisesErrorForm),
    ))


class BadgeForm(forms.ModelForm):
    class Meta:
        model = Badge
        fields = ('name', 'color',)


class BadgeMultiForm(MultiModelFormMixin):
    form_classes = {
        'badge1': BadgeForm,
        'badge2': BadgeForm,
    }


class NonModelForm(forms.Form):
    field1 = forms.CharField()


class MixedForm(MultiModelFormMixin):
    form_classes = {
        'badge': BadgeForm,
        'non_model': NonModelForm,
    }


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ('name', 'books',)


class ManyToManyMultiForm(MultiModelFormMixin):
    form_classes = {
        'badge': BadgeForm,
        'author': AuthorForm,
    }


class OptionalFileForm(forms.Form):
    myfile = forms.FileField(required=False)


class Step1Form(MultiModelFormMixin):
    # This is required because the WizardView introspects it, but we don't have
    # a way of determining this dynamically, so just set it to an empty
    # dictionary.
    base_fields = {}

    form_classes = {
        'myfile': OptionalFileForm,
        'profile': ProfileForm,
    }


class Step2Form(forms.Form):
    confirm = forms.BooleanField(required=True)


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ('name',)


BookImageFormSet = inlineformset_factory(Book, BookImage, fields=('name',))


class BookMultiForm(MultiModelFormMixin):
    form_classes = {
        'book': BookForm,
        'error': RaisesErrorForm,
        'images': BookImageFormSet,
    }

    def __init__(self, *args, **kwargs):
        instance = kwargs.pop('instance', None)
        if instance is not None:
            kwargs['instance'] = {
                'book': instance,
                'images': instance,
            }
        super(BookMultiForm, self).__init__(*args, **kwargs)


class RaisesErrorCustomCleanMultiform(UserProfileMultiForm):
    def clean(self):
        cleaned_data = super(UserProfileMultiForm, self).clean()
        raise ValidationError('It broke')
        return cleaned_data


class ModifiesDataCustomCleanMultiform(UserProfileMultiForm):
    def clean(self):
        cleaned_data = super(UserProfileMultiForm, self).clean()
        cleaned_data['profile']['display_name'] = "cleaned name"
        return cleaned_data


class BookImageMultiform(MultiModelForm):
    default_form_key = 'image'
    form_classes = {
        default_form_key: modelform_factory(BookImage, exclude=['book']),
        'example': formset_factory(NonModelForm)
    }


class BookModelMultiform(MultiModelForm):
    default_form_key = 'book'

    form_classes = {
        default_form_key: BookForm,
        'images': modelformset_factory(BookImage,
            form=BookImageMultiform, can_delete=True, can_order=False, extra=0)

    }
