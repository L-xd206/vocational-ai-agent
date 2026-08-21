from django.contrib import admin

from .models import AbilityMap, CapabilityNode


@admin.register(CapabilityNode)
class CapabilityNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "node_type", "job", "parent", "origin", "is_enabled")
    list_filter = ("node_type", "origin", "is_enabled", "organization")
    search_fields = ("name", "job__name")


admin.site.register(AbilityMap)
