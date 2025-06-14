from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

# Unregister the default User admin
admin.site.unregister(User)
# Register User with UserAdmin
admin.site.register(User, UserAdmin)