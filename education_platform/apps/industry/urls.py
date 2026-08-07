from django.urls import path

from . import views

app_name = "industry"

urlpatterns = [
    path("chain-list.html", views.page_chain_list, name="chain-list"),
    path("能力图谱库.html", views.page_chain_list, name="capability-library"),
    path("api/chain/list", views.api_chain_list, name="chain-list-api"),
    path("api/chain/create", views.api_chain_create, name="chain-create"),
    path("api/chain/<int:chain_id>/detail", views.api_chain_detail, name="chain-detail"),
    path("api/chain/<int:chain_id>/delete", views.api_chain_delete, name="chain-delete"),
    path("api/job/create", views.api_job_create, name="job-create"),
    path("api/job/<int:job_id>/update", views.api_job_update, name="job-update"),
    path("api/job/<int:job_id>/delete", views.api_job_delete, name="job-delete"),
]
