from .models import User
from django.shortcuts import get_object_or_404


def get_user_by_username(username):
    return User.objects.filter(username=username).first()


def user_by_id(user_id):
    return get_object_or_404(User, pk=user_id)


def all_users():
    return User.objects.order_by("username")
