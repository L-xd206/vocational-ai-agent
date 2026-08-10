from django.urls import path

from . import views

app_name = "capabilities"

urlpatterns = [
    path("api/ability/generate", views.api_ability_generate, name="ability-generate"),
    path("api/ability/<int:job_id>/tree", views.api_ability_tree, name="ability-tree"),
    path("api/ability/<int:job_id>/text", views.api_ability_text, name="ability-text"),
    path("api/ability/node/toggle", views.api_ability_node_toggle, name="ability-node-toggle"),
    path("api/ability/node/add", views.api_ability_node_add, name="ability-node-add"),
    path("api/ability/<int:job_id>/review", views.api_ability_review, name="ability-review"),
    path("api/ability/analysis/start", views.api_analysis_start, name="analysis-start"),
    path("api/ability/analysis/<int:batch_id>/tree", views.api_analysis_tree, name="analysis-tree"),
    path("api/ability/analysis/node/<int:node_id>/adopt", views.api_analysis_node_adopt, name="analysis-node-adopt"),
    path("api/ability/analysis/node/<int:node_id>/reject", views.api_analysis_node_reject, name="analysis-node-reject"),
    path("api/ability/analysis/rejected", views.api_rejected_analysis_tree, name="analysis-rejected"),
]
