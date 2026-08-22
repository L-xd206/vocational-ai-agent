from django.urls import path

from . import views

app_name = "teaching"
urlpatterns = [
    path("api/teaching/nodes/<int:node_id>/questions", views.api_node_questions, name="node-questions"),
]
