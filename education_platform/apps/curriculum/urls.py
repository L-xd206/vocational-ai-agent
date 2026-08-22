from django.urls import path

from . import views

app_name = "curriculum"
urlpatterns = [
    path("课程管理.html", views.page_course_management, name="course-management"),
    path("教育资源库.html", views.page_resource_library, name="resource-library"),
    path("api/curriculum/manage", views.api_course_management_trees, name="course-management-trees"),
    path("api/curriculum/owner-candidates", views.api_course_owner_candidates, name="course-owner-candidates"),
    path("api/curriculum/<int:tree_id>/owner", views.api_assign_course_owner, name="assign-course-owner"),
    path("api/curriculum/manage/<int:tree_id>", views.api_update_course, name="update-course"),
    path("api/curriculum/trees", views.api_course_task_trees, name="course-task-trees"),
    path("api/curriculum/dispatch", views.api_dispatch_abilities, name="dispatch-abilities"),
    path("api/curriculum/<int:tree_id>/ai-generate", views.api_generate_learning_tasks, name="generate-learning-tasks"),
    path("api/curriculum/<int:tree_id>/publish", views.api_publish_course_tree, name="publish-course-tree"),
    path("api/curriculum/nodes/<int:node_id>", views.api_task_card_detail, name="task-card-detail"),
]
