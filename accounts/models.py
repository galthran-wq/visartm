from django.db import models
from django.contrib.auth.models import User
from django.contrib import admin


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.TextField(null=True, blank=True)
    last_name = models.TextField(null=True, blank=True)
    assessor_rating = models.IntegerField(default=0)

    def get_profile(user):
        try:
            return Profile.objects.get(user=user)
        except BaseException:
            profile = Profile()
            profile.user = user
            profile.save()
            return profile

    def __str__(self):
        return self.user.username


admin.site.register(Profile)
