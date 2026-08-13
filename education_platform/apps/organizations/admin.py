from django.contrib import admin

from .models import Class, College, Organization, Student

admin.site.register(College)
admin.site.register(Organization)
admin.site.register(Class)
admin.site.register(Student)
