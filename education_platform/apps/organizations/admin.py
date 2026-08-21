from django.contrib import admin

from .models import Class, Organization, Student

admin.site.register(Organization)
admin.site.register(Class)
admin.site.register(Student)
