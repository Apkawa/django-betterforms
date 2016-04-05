# coding: utf-8
from __future__ import unicode_literals

import six
from django.template import Variable, VariableDoesNotExist


class ClassPropertyDescriptor(object):
    def __init__(self, fget, fset=None):
        self.fget = fget
        self.fset = fset

    def __get__(self, obj, klass=None):
        if klass is None:
            klass = type(obj)
        return self.fget.__get__(obj, klass)()

    def __set__(self, obj, value):
        if not self.fset:
            raise AttributeError("can't set attribute")
        type_ = type(obj)
        return self.fset.__get__(obj, type_)(value)

    def setter(self, func):
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.fset = func
        return self


def classproperty(func):
    if not isinstance(func, (classmethod, staticmethod)):
        func = classmethod(func)

    return ClassPropertyDescriptor(func)


_unset = object()


def resolve_path(obj, path, default=_unset):
    try:
        return Variable(path).resolve(obj)
    except VariableDoesNotExist:
        if default is _unset:
            raise AttributeError("don't resolved path `%s`" % path)
        return default


def _getattr_path(obj, path):
    if not path:
        return obj

    parts = path
    if isinstance(path, six.string_types):
        parts = path.split('.')

    attr = parts[0]
    child_path = parts[1:]

    obj = getattr(obj, attr, _unset)
    if obj is _unset:
        raise AttributeError
    return _getattr_path(obj, child_path)


def getattr_path(obj, path, default=_unset):
    try:
        return _getattr_path(obj, path)
    except AttributeError as e:
        if default is _unset:
            raise AttributeError("don't getattr path `%s`" % path)
        return default


def setattr_path(obj, path, value):
    parts = path
    if isinstance(path, six.string_types):
        parts = path.split('.')

    sub_obj = getattr_path(obj, parts[:-1])
    setattr(sub_obj, parts[-1], value)
