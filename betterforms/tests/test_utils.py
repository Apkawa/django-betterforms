# coding: utf-8
from unittest import TestCase

from ..utils import _getattr_path, getattr_path, setattr_path


class UtilTest(TestCase):
    def test_getattr_path(self):
        test = 'test'
        o = type('mock', (object, ), {'a': test})
        self.assertEqual(_getattr_path(o, 'a'), test)
        self.assertEqual(_getattr_path(o, 'a.upper'), test.upper)


    def test_getattr_attribute_error(self):
        test = 'test'
        o = type('mock', (object, ), {'a': test})

        self.assertRaises(AttributeError, _getattr_path, *(o, 'b'))
        self.assertRaises(AttributeError, _getattr_path, *(o, 'a.b'))

    def test_setattr_path(self):
        test = 'test'
        test2 = '123'
        c = type('mock', (object, ), {'c': test})
        b = type('mock', (object, ), {'b': c})
        a = type('mock', (object, ), {'a': b})

        self.assertEqual(getattr_path(a, 'a.b.c'), test)
        setattr_path(a, 'a.b.c', test2)
        self.assertEqual(getattr_path(a, 'a.b.c'), test2)

        setattr_path(a, 'a.b._test', test2)
        self.assertEqual(getattr_path(a, 'a.b._test'), test2)




