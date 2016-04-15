# coding: utf-8
from __future__ import unicode_literals

from collections import OrderedDict

from django.test.client import RequestFactory
from django.views.generic import CreateView
from django.core import urlresolvers
from django.utils.encoding import force_text

from ..models import User, Profile, Badge, Book

from ..forms import (
    UserProfileMultiForm, BadgeMultiForm, ErrorMultiForm,
    MixedForm, NeedsFileField, ManyToManyMultiForm, Step2Form,
    BookMultiForm, RaisesErrorCustomCleanMultiform,
    ModifiesDataCustomCleanMultiform,
)

from .utils import TestCase


class ModelTestTest(TestCase):
    pass
