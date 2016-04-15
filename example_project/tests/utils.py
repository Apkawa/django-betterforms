# coding: utf-8
from __future__ import unicode_literals

import unittest

from django.test import TestCase as DjangoTestCase


class TestCase(type(b"TestCase", (DjangoTestCase,), {}), unittest.TestCase):
    pass
