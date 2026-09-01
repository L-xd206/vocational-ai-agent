from django.urls import path

from . import views

app_name = "teaching"
urlpatterns = [
    path("api/teaching/nodes/<int:node_id>/questions", views.api_node_questions, name="node-questions"),
    # 教学安排
    path("教学安排.html", views.page_teaching_arrangement, name="teaching-arrangement-page"),
    path("api/teaching-arrangements", views.api_teaching_arrangement_list, name="teaching-arrangement-list"),
    path("api/teaching-arrangements/course-options", views.api_teaching_course_options, name="teaching-course-options"),
    path("api/teaching-arrangements/class-options", views.api_teaching_class_options, name="teaching-class-options"),
    path("api/teaching-arrangements/<int:arrangement_id>", views.api_teaching_arrangement_detail, name="teaching-arrangement-detail"),
    path("api/teaching-arrangements/<int:arrangement_id>/members", views.api_teaching_arrangement_members, name="teaching-arrangement-members"),
    # 课程试题检索
    path("试题库.html", views.page_question_bank, name="question-bank-page"),
    path("api/teaching/questions/course-options", views.api_question_course_options, name="question-course-options"),
    path("api/teaching/questions", views.api_question_list, name="question-list"),
]
