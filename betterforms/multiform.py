import copy
from itertools import chain
from operator import add

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from django.db import models

from collections import defaultdict

from django.forms.models import modelform_factory

from betterforms.utils import classproperty

try:
    from collections import OrderedDict
except ImportError:  # Python 2.6, Django < 1.7
    from django.utils.datastructures import SortedDict as OrderedDict  # NOQA

try:
    from django.forms.utils import ErrorDict, ErrorList
except ImportError:  # Django < 1.7
    from django.forms.util import ErrorDict, ErrorList  # NOQA

from django.core.exceptions import ValidationError
from django.utils.encoding import python_2_unicode_compatible
from django.utils.safestring import mark_safe
from django.utils.six.moves import reduce


@python_2_unicode_compatible
class MultiFormMixin(object):
    """
    A container that allows you to treat multiple forms as one form.  This is
    great for using more than one form on a page that share the same submit
    button.  MultiForm imitates the Form API so that it is invisible to anybody
    else that you are using a MultiForm.
    """
    form_classes = {}
    field_form_map = None

    class Meta:
        fields = None
        exclude = None
        widgets = None
        formfield_callback = None
        localized_fields = None
        labels = None
        help_texts = None
        error_messages = None

    @classproperty
    def _meta(cls):
        return cls.Meta

    def __init__(self, data=None, files=None, *args, **kwargs):
        # Some things, such as the WizardView expect these to exist.
        self.data, self.files = data, files
        kwargs.update(
            data=data,
            files=files,
        )
        self.error_class = kwargs.pop('error_class', ErrorList)
        self.initials = self.get_initials(initial=kwargs.pop('initial', None), *args, **kwargs)
        self.crossform_errors = []

        self.args, self.kwargs = args, kwargs

        self._init(*args, **kwargs)

        self._errors = None
        self._changed_data = None

    def _init(self, *args, **kwargs):
        self.forms = self.get_forms(*args, **kwargs)

        self.fields = self._get_fields()
        self.aliased_fields = self._get_aliased_fields()

    def _build_field_name(self, name, prefix):
        return "%s_%s" % (prefix, name)

    def _update_field_form_map(self, form_key, form):
        if self.field_form_map is None:
            self.field_form_map = {}

        field_form_map = self.field_form_map
        for f_name, field in form.base_fields.items():
            field_form_map[f_name] = form_key
            field_form_map[self._build_field_name(f_name, self.get_form_prefix(form_key))] = form_key

    def _get_aliased_fields(self):
        fields = defaultdict(list)
        for form in self.forms.values():
            for f in form:
                fields[f.name].append(f)
        return dict(fields)

    def _get_fields(self):
        fields = {}
        for form in self.forms.values():
            for f in form:
                fields[self._build_field_name(f.name, form.prefix)] = f
        return fields

    def get_initials(self, initial=None, *args, **kwargs):
        initials = initial or {}
        if initials and not all([isinstance(v, dict) for v in initials.values()]):
            initials = {None: initials}
        return initials

    def get_form_classes(self, *args, **kwargs):
        """
        :return: dict
        """
        return dict(self.form_classes)

    def _build_form_class(self, key, base_form_class):
        return base_form_class

    def get_forms(self, *args, **kwargs):
        forms = OrderedDict()
        for key, form_class in self.get_form_classes(*args, **kwargs).items():
            self._update_field_form_map(key, form_class)
            fargs, fkwargs = self.get_form_args_kwargs(key, args, kwargs)
            form_class = self._build_form_class(key, form_class)
            forms[key] = form_class(*fargs, **fkwargs)
        return forms

    def get_form_prefix(self, form_key):
        prefix = self.kwargs.get('prefix')
        if prefix is None:
            prefix = form_key
        else:
            prefix = '{0}_{1}'.format(form_key, prefix)

        return prefix

    def get_form_args_kwargs(self, key, args, kwargs):
        """
        Returns the args and kwargs for initializing one of our form children.
        """
        fkwargs = kwargs.copy()

        fkwargs.update(
            initial=self.initials.get(key),
            prefix=self.get_form_prefix(key),
        )
        return args, fkwargs

    def __str__(self):
        return self.as_table()

    def __getitem__(self, key):
        try:
            return self.fields[key]
        except KeyError:
            fields = self.aliased_fields[key]
            if len(fields) > 1:
                raise KeyError("Fields '%s' more than 1" % key)
            return fields[0]

    def __iter__(self):
        # TODO: Should the order of the fields be controllable from here?
        return chain.from_iterable(self.forms.values())

    @property
    def changed_data(self):
        if self._changed_data is None:
            self._changed_data = list(chain.from_iterable(form.changed_data for form in self.forms.values()))
        return self._changed_data

    @property
    def is_bound(self):
        return any(form.is_bound for form in self.forms.values())

    def clean(self):
        """
        Raises any ValidationErrors required for cross form validation. Should
        return a dict of cleaned_data objects for any forms whose data should
        be overridden.
        """
        return self.cleaned_data

    @property
    def errors(self):
        if self._errors is None:
            self._errors = self.full_clean()
        return self._errors

    def full_clean(self):
        errors = ErrorDict()
        for form in self.forms.values():
            if form.errors:
                for key, error_list in form.errors.items():
                    names = [key, self._build_field_name(key, form.prefix)]
                    for _k in names:
                        if _k not in errors:
                            if key == NON_FIELD_ERRORS:
                                errors[_k] = self.error_class(error_class='nonfield')
                            else:
                                errors[_k] = self.error_class()
                        errors[_k].extend(error_list)
        return errors

    def add_crossform_error(self, e):
        self.crossform_errors.append(e)

    def is_valid(self):
        forms_valid = all(form.is_valid() for form in self.forms.values())
        try:
            cleaned_data = self.clean()
        except ValidationError as e:
            self.add_crossform_error(e)
        else:
            if cleaned_data is not None:
                for key, data in cleaned_data.items():
                    self.forms[key].cleaned_data = data
        return forms_valid and not self.crossform_errors

    def non_field_errors(self):
        form_errors = (
            form.non_field_errors() for form in self.forms.values()
            if hasattr(form, 'non_field_errors')
        )
        return ErrorList(chain(self.crossform_errors, *form_errors))

    def as_table(self):
        return mark_safe(''.join(form.as_table() for form in self.forms.values()))

    def as_ul(self):
        return mark_safe(''.join(form.as_ul() for form in self.forms.values()))

    def as_p(self):
        return mark_safe(''.join(form.as_p() for form in self.forms.values()))

    def is_multipart(self):
        return any(form.is_multipart() for form in self.forms.values())

    @property
    def media(self):
        return reduce(add, (form.media for form in self.forms.values()))

    def hidden_fields(self):
        # copy implementation instead of delegating in case we ever
        # want to override the field ordering.
        return [field for field in self if field.is_hidden]

    def visible_fields(self):
        return [field for field in self if not field.is_hidden]

    @property
    def cleaned_data(self):
        return OrderedDict(
            (key, form.cleaned_data)
            for key, form in self.forms.items() if form.is_valid()
        )

    @cleaned_data.setter
    def cleaned_data(self, data):
        for key, value in data.items():
            self.forms[key].cleaned_data = value


class MultiModelFormMixin(MultiFormMixin):
    """
    MultiModelForm adds ModelForm support on top of MultiForm.  That simply
    means that it includes support for the instance parameter in initialization
    and adds a save method.
    """

    default_instance_key = None

    class Meta(MultiFormMixin.Meta):
        model = None

    def __init__(self, *args, **kwargs):
        self.instances = self.get_instances(kwargs.pop('instance', None), *args, **kwargs)
        if self.instances is None:
            self.instances = {}
        # default instance
        self.instance = self.get_default_instance()
        super(MultiModelFormMixin, self).__init__(*args, **kwargs)
        if self.kwargs['data']:
            self._init(*self.args, **self.kwargs)

    def get_instances(self, instance=None, *args, **kwargs):
        instances = instance or {}
        if isinstance(instance, models.Model):
            instances = {self.default_instance_key: instance}
        return instances

    def get_default_instance(self):
        return self.instances.get(self.default_instance_key)

    def _build_form_class(self, form_key, base_form_class):
        defaults = dict.fromkeys(['fields', 'exclude', 'widgets', 'model'])
        for opt_key in defaults:
            meta_opt = getattr(self.Meta, opt_key, None)
            if isinstance(meta_opt, dict) and form_key in meta_opt:
                meta_opt = meta_opt[form_key]
            else:
                cleaned_meta_opt = []
                if self.field_form_map and meta_opt and opt_key in ['fields', 'exclude']:
                    for _f in meta_opt:
                        if self.field_form_map.get(_f) == form_key:
                            cleaned_meta_opt.append(_f)
                    if cleaned_meta_opt:
                        meta_opt = cleaned_meta_opt

                elif form_key != self.default_instance_key:
                    continue

            defaults[opt_key] = meta_opt

        model = defaults.pop('model', None)
        if model:
            if form_key == self.default_instance_key:
                # maybe admin.site
                defaults['formfield_callback'] = getattr(self, 'formfield_callback', None)
            return modelform_factory(model, **defaults)
        return base_form_class

    def get_form_args_kwargs(self, key, args, kwargs):
        fargs, fkwargs = super(MultiModelFormMixin, self).get_form_args_kwargs(key, args, kwargs)
        try:
            # If we only pass instance when there was one specified, we make it
            # possible to use non-ModelForms together with ModelForms.
            fkwargs['instance'] = self.instances[key]
        except KeyError:
            pass
        return fargs, fkwargs

    def save_multiform(self, commit=True):
        objects = OrderedDict(
            (key, form.save(commit))
            for key, form in self.forms.items()
        )

        if any(hasattr(form, 'save_m2m') for form in self.forms.values()):
            def save_m2m():
                for form in self.forms.values():
                    if hasattr(form, 'save_m2m'):
                        form.save_m2m()

            self.save_m2m = save_m2m

        return objects

    def save(self, commit=True):
        objects = self.save_multiform(commit=commit)
        return objects[self.default_instance_key]


class MultiForm(forms.BaseForm, MultiFormMixin):
    pass


class MultiModelForm(MultiModelFormMixin, forms.BaseModelForm):
    pass
