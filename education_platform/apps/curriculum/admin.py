from django.contrib import admin

from .models import CourseTree, CourseTreeNode


@admin.register(CourseTree)
class CourseTreeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "course_type",
        "total_hours",
        "credits",
        "organization",
        "source_ability",
        "owner",
        "is_published",
        "updated_at",
    )
    list_filter = ("organization", "course_type", "is_published")
    search_fields = ("name", "textbook__name", "source_ability__name", "owner__username")


@admin.register(CourseTreeNode)
class CourseTreeNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "node_type", "tree", "parent", "is_edited", "sort_order")
    list_filter = ("node_type", "is_edited")
    search_fields = ("name", "task_description", "work_scenario")
