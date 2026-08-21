from django.contrib import admin

from .models import Textbook, TextbookNode


@admin.register(Textbook)
class TextbookAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "edition", "organization", "publisher", "updated_at")
    list_filter = ("organization",)
    search_fields = ("name", "edition", "publisher", "isbn")


@admin.register(TextbookNode)
class TextbookNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "node_type", "textbook", "parent", "sort_order")
    list_filter = ("node_type", "textbook")
    search_fields = ("name", "content")
