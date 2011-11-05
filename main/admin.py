from tobaccocessation.main.models import *
from django.contrib import admin

class UserProfileAdmin(admin.ModelAdmin):
  list_display = ('display_name',)

admin.site.register(UserProfile, UserProfileAdmin)