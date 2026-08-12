from django.urls import path

from . import views

app_name = "collection"

urlpatterns = [
    path("api/collection/sources", views.api_crawl_sources, name="crawl-sources"),
    path(
        "api/collection/sources/<int:source_id>",
        views.api_crawl_source_detail,
        name="crawl-source-detail",
    ),
    path("api/collection/tasks", views.api_crawl_tasks, name="crawl-tasks"),
    path("api/crawl/start", views.api_crawl_start, name="crawl-start"),
    path("api/crawl/<int:task_id>/status", views.api_crawl_status, name="crawl-status"),
    path("api/collection/analysis/start", views.api_analysis_start, name="analysis-start"),
    path(
        "api/collection/analysis/latest-trees",
        views.api_latest_analysis_trees,
        name="analysis-latest-trees",
    ),
    path("api/collection/analysis/<int:batch_id>/tree", views.api_analysis_tree, name="analysis-tree"),
    path(
        "api/collection/analysis/nodes/<int:node_id>/adopt",
        views.api_analysis_node_adopt,
        name="analysis-node-adopt",
    ),
    path(
        "api/collection/analysis/nodes/<int:node_id>/reject",
        views.api_analysis_node_reject,
        name="analysis-node-reject",
    ),
    path(
        "api/collection/rejected-nodes",
        views.api_rejected_analysis_tree,
        name="analysis-rejected",
    ),
]
