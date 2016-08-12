from django.db import models


class User(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()


class Profile(models.Model):
    user = models.OneToOneField('User', related_name='profile', on_delete=models.CASCADE)

    display_name = models.CharField(max_length=255, blank=True)


class Badge(models.Model):
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=20)


class Author(models.Model):
    name = models.CharField(max_length=255)
    books = models.ManyToManyField('Book', related_name='authors')


class Book(models.Model):
    name = models.CharField(max_length=255)


class BookImage(models.Model):
    book = models.ForeignKey(Book, related_name='images', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
