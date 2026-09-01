from django.urls import path

from . import views

app_name = "learning"
urlpatterns = [
    path("学习计划.html", views.page_learning_plan, name="learning-plan-page"),
    path("学习档案.html", views.page_learning_profile, name="learning-profile-page"),
    path("api/learning-plans", views.api_learning_plan_list, name="learning-plan-list"),
    path("api/learning-plans/<int:plan_id>", views.api_learning_plan_detail, name="learning-plan-detail"),
    path("api/learning-profile", views.api_learning_profile, name="learning-profile"),
]
