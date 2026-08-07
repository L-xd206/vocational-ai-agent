from django.urls import path

from . import views

app_name = "organizations"
urlpatterns = [
    path("api/organizations/colleges", views.api_college_list, name="college-list"),
]
