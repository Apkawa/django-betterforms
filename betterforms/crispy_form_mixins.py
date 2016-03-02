# coding: utf-8
from __future__ import unicode_literals

import copy

from crispy_forms.layout import Layout, Div, Submit, HTML, Button, Row, Field, Fieldset, ButtonHolder
from crispy_forms.bootstrap import AppendedText, PrependedText, FormActions
from crispy_forms.helper import FormHelper, Layout


class CrispyFormHelperMixin(object):
    fieldsets = None
    helper = None

    def build_helper_fieldset(self, fieldsets):
        layout_args = []
        for header, _fieldset in fieldsets:
            _fieldset_args = []
            if isinstance(_fieldset, (tuple, list)):
                # looks like child fieldset
                layout_args.append(Layout(*self.build_helper_fieldset(_fieldset)))

            for _field in _fieldset['fields']:
                if isinstance(_field, (tuple, list)):
                    row = Div(
                        *_field,
                        css_class='form-row form-group field-box col-sm-%s' % (12 / len(_field)))
                else:
                    row = Div(
                        *_field,
                        css_class='form-row form-group')

                _fieldset_args.append(row)
            layout_args.append(Fieldset(header, *_fieldset_args, css_class=_fieldset.get('classes')))
        return layout_args

    def build_helper(self):
        helper = FormHelper()
        fieldsets = self.get_fieldset()
        helper.add_layout(Layout(*self.build_helper_fieldset(fieldsets)))
        return helper

    def get_fieldset(self):
        return copy.copy(self.fieldsets)

    def get_helper(self):
        if self.helper:
            return self.helper

        if self.fieldsets:
            return self.build_helper()

        else:
            # uni
            return FormHelper(self)


class CrispyMultiFormHelperMixin(CrispyFormHelperMixin):
    def flattened_fieldsets(self, fieldsets):
        new_fieldsets = []
        for header, fieldset in fieldsets:
            if isinstance(fieldset, (tuple, list)):
                new_fieldsets.append(self.flattened_fieldsets(fieldset))
            new_fields = []
            for field in fieldset['fields']:
                if field.startswith('#'):
                    _form = self.forms[field.strip('#')]
                    form_fieldsets = getattr(_form, 'fieldsets')
                    if not form_fieldsets:
                        pass
                else:
                    new_fields.append(field)
        return new_fieldsets

    def get_fieldset(self):
        fieldset = super(CrispyMultiFormHelperMixin, self).get_fieldset()
        if fieldset:
            pass

    def get_helper(self):
        if self.helper:
            return self.helper

        if self.fieldsets:
            return self.build_helper()

        else:
            helper = FormHelper()
            helper.layout = Layout(*[FormHelper(f).layout for f in self.forms.values()])
            return helper
