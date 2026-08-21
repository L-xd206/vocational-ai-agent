from django.urls import path

from . import views

app_name = "curriculum"
urlpatterns = [
    path("api/curriculum/dispatch", views.api_dispatch_abilities, name="dispatch-abilities"),
]
