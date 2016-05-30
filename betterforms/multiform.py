import copy
from itertools import chain
from operator import add

from django import forms
from django.forms.forms import BoundField
from django.core.exceptions import NON_FIELD_ERRORS

from django.db import models

from collections import defaultdict

from django.db.transaction import atomic
from django.forms.formsets import DELETION_FIELD_NAME, ORDERING_FIELD_NAME
from django.forms.models import modelform_factory

from betterforms.utils import classproperty, getattr_path, setattr_path, depth_save_relations

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

from .decorators import lru_cache


class CallbackDict(dict):
    def __init__(self, _d, get_callback=None, set_callback=None):
        self._get_callback = get_callback
        self._set_callback = set_callback
        super(CallbackDict, self).__init__(_d)

    def __getitem__(self, item):
        if callable(self._get_callback):
            ret = self._get_callback(self, item)
            if ret is not None:
                return ret
        return super(CallbackDict, self).__getitem__(item)

    def __setitem__(self, key, value):
        if callable(self._set_callback):
            ret = self._set_callback(self, key, value)
            if ret is not None:
                return ret
        super(CallbackDict, self).__setitem__(key, value)


@python_2_unicode_compatible
class MultiFormMixin(object):
    """
    A container that allows you to treat multiple forms as one form.  This is
    great for using more than one form on a page that share the same submit
    button.  MultiForm imitates the Form API so that it is invisible to anybody
    else that you are using a MultiForm.
    """
    default_form_key = None

    form_classes = {}
    field_form_map = None

    required = None

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

    @property
    @lru_cache(maxsize=30)
    def _form_classes(self):
        return self.get_form_classes(*self.args, **self.kwargs)

    @property
    def default_form(self):
        return self.forms[self.default_key]

    def __init__(self, data=None, files=None, auto_id='id_%s', *args, **kwargs):
        # Some things, such as the WizardView expect these to exist.
        self.data, self.files = data, files
        kwargs.update(
            data=data,
            files=files,
        )
        self.prefix = kwargs.get('prefix')
        self.auto_id = auto_id
        self.initial = kwargs.get('initial', {})
        self.error_class = kwargs.pop('error_class', ErrorList)
        self.initials = self.get_initials(initial=kwargs.pop('initial', None), *args, **kwargs)
        self.crossform_errors = []

        self.args, self.kwargs = args, kwargs

        self._init(*args, **kwargs)

        self._errors = None
        self._changed_data = None

    def _init(self, *args, **kwargs):
        self.forms = self.get_forms(*args, **kwargs)
        self._fields = self._get_fields()
        self._form_fields = {}
        self.aliased_fields = self._get_aliased_fields()
        self.aliased_fields.update(self._get_aliased_forms())

    def _build_field_name(self, name, prefix):
        return "%s_%s" % (prefix, name)

    def _update_field_form_map(self, form_key, form_class):
        if issubclass(form_class, forms.BaseFormSet):
            return
        if self.field_form_map is None:
            self.field_form_map = {}

        field_form_map = self.field_form_map
        for f_name, field in form_class.base_fields.items():
            field_form_map[f_name] = form_key
            field_form_map[self._build_field_name(f_name, self.get_form_prefix(form_key))] = form_key

    def _get_aliased_fields(self):
        fields = defaultdict(list)
        for form_key, form in self.forms.items():
            if isinstance(form, forms.BaseFormSet):
                # fields[form_key].append(form)
                continue
            for f in form:
                fields[f.name].append(f)
        return dict(fields)

    def _get_aliased_forms(self):
        _forms_map = defaultdict(list)
        for f_name, form in self.forms.items():
            form_key = f_name + '_form'
            if isinstance(form, forms.BaseFormSet):
                form_key = f_name + '_formset'

            _forms_map[form_key] = form
        return _forms_map

    def _get_fields(self):
        fields = {}
        for form_key, form in self.forms.items():
            if isinstance(form, forms.BaseFormSet):
                # fields[self._build_field_name(form_key, form.prefix)] = form
                continue

            for f in form:
                fields[self._build_field_name(f.name, form.prefix)] = f
        return fields

    def get_initials(self, initial=None, *args, **kwargs):
        initials = initial or {}
        if initials and not all([isinstance(v, dict) for v in initials.values()]):
            initials = {self.default_form_key: initials}
        return initials

    def get_required_forms(self):
        if self.required is None:
            return self.forms.keys()
        return self.required

    def get_form_classes(self, *args, **kwargs):
        """
        :return: dict
        """
        return dict(self.form_classes)

    def _build_form_class(self, key, base_form_class):
        return base_form_class

    def get_forms(self, *args, **kwargs):
        forms = OrderedDict()
        for key, form_class in self._form_classes.items():
            self._update_field_form_map(key, form_class)
            fargs, fkwargs = self.get_form_args_kwargs(key, form_class, args, kwargs)
            form_class = self._build_form_class(key, form_class)
            forms[key] = form_class(*fargs, **fkwargs)
        return forms

    def get_form_prefix(self, form_key):
        prefix = self.kwargs.get('prefix')
        if prefix is None:
            prefix = form_key
        elif form_key != self.default_key:
            prefix = '{0}_{1}'.format(form_key, prefix)
        return prefix

    def get_form_args_kwargs(self, key, form_class, args, kwargs):
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

    @property
    def fields(self):
        def set_callback(_d, key, field):
            self._set_field(key, field)
            return False

        return CallbackDict(self._fields, set_callback=set_callback)

    def _get_field(self, name):
        try:
            return self.fields[name]
        except KeyError:
            fields = self.aliased_fields[name]
            if isinstance(fields, (forms.BaseFormSet, forms.BaseForm)):
                return fields

            if len(fields) > 1:
                raise KeyError("Fields '%s' more than 1" % name)
            return fields[0]

    def _set_field(self, name, field):
        default_form = self.default_form
        default_form.fields[name] = field
        bound_field = default_form[name]

        if name not in self.aliased_fields:
            self.aliased_fields[name] = []

        self.aliased_fields[name].append(bound_field)
        field_name = self._build_field_name(name, self.prefix)
        self._fields[field_name] = bound_field

    def __getitem__(self, key):
        return self._get_field(key)

    def __setitem__(self, key, field):
        self._set_field(key, field)

    def __iter__(self):
        # TODO: Should the order of the fields be controllable from here?
        return chain.from_iterable(self.forms.values() + [self._form_fields.values()])

    @property
    def changed_data(self):
        if self._changed_data is None:
            _changed_data = []
            for form in self.cleaned_forms.values():
                if isinstance(form, forms.BaseFormSet):
                    _changed_data.append([f.changed_data for f in form])
                else:
                    _changed_data.append(form.changed_data)
            self._changed_data = list(chain.from_iterable(_changed_data))
        return self._changed_data

    def has_changed(self):
        return any(form.has_changed() for form in self.cleaned_forms.values())

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

    def clean_forms(self):
        required_forms = set(self.get_required_forms())
        forms = dict(self.forms)
        for key, form in forms.items():
            if not form.has_changed() and key not in required_forms:
                del forms[key]
            else:
                print key
        return forms

    @property
    def cleaned_forms(self):
        cleaned_forms = getattr(self, '_cleaned_forms', None)
        if not cleaned_forms:
            cleaned_forms = self.clean_forms()
            setattr(self, '_cleaned_forms', cleaned_forms)
        return cleaned_forms

    def full_clean(self):
        errors = ErrorDict()
        for form in self.cleaned_forms.values():
            if form.errors:
                if isinstance(form, forms.BaseFormSet):
                    all_form_errors = form.errors
                else:
                    all_form_errors = [form.errors]
                for form_error in all_form_errors:
                    for key, error_list in form_error.items():
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
        forms_valid = all(form.is_valid() for form in self.cleaned_forms.values())

        try:
            cleaned_data = self.clean()
        except ValidationError as e:
            self.add_crossform_error(e)
        else:
            if cleaned_data is not None:
                for key, data in cleaned_data.items():
                    form = self.forms[key]
                    if isinstance(form, forms.BaseFormSet):
                        map_data = {}
                        for d in data:
                            _ins = d.get('id')
                            if _ins:
                                map_data['id'] = _ins.id

                        for i, _form in enumerate(form.forms):
                            obj_id = _form.instance and _form.instance.id
                            _form.cleaned_data = map_data.get(obj_id) or data[i]
                    else:
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
        return [field for field in self if getattr(field, 'is_hidden', None)]

    def visible_fields(self):
        return [field for field in self if getattr(field, 'is_hidden', None)]

    @property
    def cleaned_data(self):
        return OrderedDict(
            (key, form.cleaned_data)
            for key, form in self.cleaned_forms.items() if form.is_valid()
        )

    @cleaned_data.setter
    def cleaned_data(self, data):
        for key, value in data.items():
            form = self.forms[key]
            if isinstance(form, forms.BaseFormSet):
                map_data = {}
                for d in value:
                    _ins = d.get('id')
                    if _ins:
                        map_data['id'] = _ins.id

                for i, _form in enumerate(form.forms):
                    obj_id = _form.instance and _form.instance.id
                    _form.cleaned_data = map_data.get(obj_id) or value[i]
            else:
                form.cleaned_data = value

    @classproperty
    def base_fields(cls):
        # TODO dynamic fields
        base_fields = {}
        for form_key, form in cls.form_classes.items():
            for f_name, field in form.base_fields.items():
                base_fields['_'.join([form_key, f_name])] = field
        return base_fields

    @property
    def default_key(self):
        return self.default_form_key


class MultiModelFormMixin(MultiFormMixin):
    """
    MultiModelForm adds ModelForm support on top of MultiForm.  That simply
    means that it includes support for the instance parameter in initialization
    and adds a save method.
    """

    default_instance_key = None

    class Meta(MultiFormMixin.Meta):
        model = None
        exclude = []

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
        instances_map = instance or {}
        if isinstance(instance, models.Model):
            instances_map = {self.default_key: instance}
        else:
            instance = instances_map.get(self.default_key)

        for key in self.form_classes:
            result = self.get_instance(instance, key, *args, **kwargs)
            if result is False:
                continue
            instances_map[key] = result
        return instances_map

    def get_instance(self, instance, key, *args, **kwargs):
        if key == self.default_key:
            return instance
        else:
            try:
                instance = getattr_path(instance, key)
                if isinstance(instance, models.Manager):
                    return instance.filter()
                return instance
            except AttributeError:
                pass
        return False

    def get_default_instance(self):
        return self.instances.get(self.default_key)

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

                elif form_key != self.default_key:
                    continue

            defaults[opt_key] = meta_opt

        model = defaults.pop('model', None)
        if model:
            if form_key == self.default_key:
                # maybe admin.site
                defaults['formfield_callback'] = getattr(self, 'formfield_callback', None)
            defaults['form'] = base_form_class
            return modelform_factory(model, **defaults)
        return base_form_class

    def get_form_args_kwargs(self, key, form_class, args, kwargs):
        fargs, fkwargs = super(MultiModelFormMixin, self).get_form_args_kwargs(key, form_class, args, kwargs)
        try:
            if issubclass(form_class, forms.BaseModelFormSet):
                fkwargs['queryset'] = self.instances[key]
            else:
                fkwargs['instance'] = self.instances[key]
        except KeyError:
            pass
        return fargs, fkwargs

    def save_object(self, obj, key, objects, commit=True):
        default_key = self.default_key
        if key == default_key:
            for sub_key, sub_obj in objects.items():
                if sub_key == default_key:
                    continue
                if isinstance(sub_obj, list):
                    continue

                setattr_path(obj, sub_key, sub_obj)
        else:
            if commit:
                if isinstance(obj, list):
                    new_obj_list = []
                    for o in obj:
                        if getattr(o, 'DO_DELETE', False):
                            o.delete()
                        else:
                            depth_save_relations(o)
                            new_obj_list.append(o)
                    obj = new_obj_list
                else:
                    depth_save_relations(obj)
        return obj

    @property
    def cleaned_objects(self):
        objects = OrderedDict()
        for key, form in self.cleaned_forms.items():
            if isinstance(form, forms.BaseFormSet):
                obj_list = []
                for f in form:

                    c_data = f.cleaned_data
                    if isinstance(f, MultiFormMixin):
                        c_data = c_data[f.default_key]

                    if isinstance(f, (forms.BaseModelForm, MultiModelFormMixin)):
                        obj = f.save(commit=False)
                        is_delete = c_data.get(DELETION_FIELD_NAME)
                        setattr(obj, 'DO_DELETE', is_delete)
                        setattr(obj, 'DO_ORDER', c_data.get(ORDERING_FIELD_NAME))
                        obj_list.append(obj)

                objects[key] = obj_list
            else:
                if isinstance(form, (forms.BaseModelForm, MultiModelFormMixin)):
                    objects[key] = form.save(commit=False)
        return objects

    def save_objects(self, objects, commit=True):
        commit = True
        default_key = self.default_key
        for key, obj in objects.items():
            if key == default_key:
                continue
            self.save_object(obj, key, objects, commit=commit)

        instance = objects[default_key]
        self.save_object(instance, default_key, objects, commit=commit)
        if commit:
            instance.save()

        return objects

    def save_multiform(self, commit=True):
        objects = self.cleaned_objects
        objects = self.save_objects(objects, commit=commit)

        if any(hasattr(form, 'save_m2m') for form in self.cleaned_forms.values()):
            def save_m2m():
                for form in self.cleaned_forms.values():
                    if hasattr(form, 'save_m2m'):
                        form.save_m2m()

            self.save_m2m = save_m2m

        return objects

    def save(self, commit=True):
        objects = self.save_multiform(commit=commit)
        return objects[self.default_key]

    @property
    def default_key(self):
        return self.default_instance_key or self.default_form_key


class MultiForm(forms.BaseForm, MultiFormMixin):
    pass


class MultiModelForm(MultiModelFormMixin, forms.BaseModelForm):
    pass
