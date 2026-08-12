from django.contrib import admin

from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask, JobListing


@admin.register(CrawlSource)
class CrawlSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "code", "interval_minutes", "is_enabled", "next_run_at")
    list_filter = ("is_enabled",)
    search_fields = ("name", "code")


@admin.register(CrawlTask)
class CrawlTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "source", "trigger_type", "status", "total_results", "new_results")
    list_filter = ("status", "trigger_type", "source")
    search_fields = ("job__name",)


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "company", "job", "crawl_source", "last_seen_at")
    list_filter = ("crawl_source", "city")
    search_fields = ("title", "company", "requirements")


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
