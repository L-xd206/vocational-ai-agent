from django.contrib import admin

from .models import LearningPlan, LearningRecord, PlanDeleteLog

admin.site.register(LearningPlan)
admin.site.register(PlanDeleteLog)
admin.site.register(LearningRecord)
