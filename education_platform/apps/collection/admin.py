from django.contrib import admin

from .models import AnalysisBatch, AnalysisNode


@admin.register(AnalysisBatch)
class AnalysisBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "status", "input_listing_count", "created_at", "finished_at")
    list_filter = ("status", "model_name")
    search_fields = ("job__name",)


@admin.register(AnalysisNode)
class AnalysisNodeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "node_type", "batch", "matched_node", "decision_status")
    list_filter = ("node_type", "decision_status")
    search_fields = ("name", "batch__job__name")
