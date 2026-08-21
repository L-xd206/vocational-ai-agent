from django.contrib import admin

from .models import CourseQuestion


@admin.register(CourseQuestion)
class CourseQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "short_stem", "question_type", "difficulty", "node", "updated_at")
    list_filter = ("question_type", "difficulty")
    search_fields = ("stem", "analysis")

    @admin.display(description="题干")
    def short_stem(self, obj):
        return obj.stem[:40]
