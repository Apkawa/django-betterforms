try:
    __version__ = __import__('pkg_resources').get_distribution('django-betterforms').version
except Exception:
    __version__ = 'dev'


