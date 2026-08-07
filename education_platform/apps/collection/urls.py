from django.urls import path

from . import views

app_name = "collection"

urlpatterns = [
    path("api/crawl/start", views.api_crawl_start, name="crawl-start"),
    path("api/crawl/<int:task_id>/status", views.api_crawl_status, name="crawl-status"),
]
