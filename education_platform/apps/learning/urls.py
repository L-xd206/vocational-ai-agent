from django.urls import path

from . import views

app_name = "learning"
urlpatterns = [
    path("学习计划.html", views.page_learning_plan, name="learning-plan-page"),
    path("学习档案.html", views.page_learning_profile, name="learning-profile-page"),
    path("计划详情.html", views.page_learning_plan_content, name="learning-plan-content-page"),
    path("计划调整.html", views.page_plan_adjust, name="plan-adjust-page"),
    path("新增计划.html", views.page_plan_create, name="plan-create-page"),
    path("api/learning-plans/<int:plan_id>/adjust", views.api_plan_adjust, name="plan-adjust"),
    path("api/learning-plans", views.api_learning_plan_list, name="learning-plan-list"),
    path("api/learning-plans/course-library", views.api_course_library, name="course-library"),
    path("api/learning-plans/from-courses", views.api_learning_plan_from_courses, name="learning-plan-from-courses"),
    path("api/learning-plans/<int:plan_id>", views.api_learning_plan_detail, name="learning-plan-detail"),
    path("api/learning-plans/<int:plan_id>/detail", views.api_learning_plan_content, name="learning-plan-content"),
    path("api/learning-plans/<int:plan_id>/progress", views.api_learning_plan_progress, name="learning-plan-progress"),
    path("api/learning-profile", views.api_learning_profile, name="learning-profile"),
    # 测评系统
    path("api/assessments/start", views.api_assessment_start, name="assessment-start"),
    path("api/assessments/submit", views.api_assessment_submit, name="assessment-submit"),
    path("api/assessments/history", views.api_assessment_history, name="assessment-history"),
    path("api/assessments/<int:run_id>", views.api_assessment_detail, name="assessment-detail"),
    # 薄弱分析
    path("api/learning-plans/<int:plan_id>/ai-weakness", views.api_ai_weakness, name="ai-weakness"),
    # 新增计划向导（按岗位 / AI 目标推荐 / 摸底）
    path("api/learning-plans/job-options", views.api_job_options, name="job-options"),
    path("api/learning-ai/chat", views.api_ai_chat, name="ai-chat"),
    path("api/learning-ai/plan-from-chat", views.api_ai_plan_from_chat, name="ai-plan-from-chat"),
    path("api/learning-plans/placement", views.api_placement_test, name="placement-test"),
    path("api/learning-plans/placement-submit", views.api_placement_submit, name="placement-submit"),
]
