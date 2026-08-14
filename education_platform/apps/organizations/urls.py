from django.urls import path

from . import views

app_name = "organizations"
urlpatterns = [
    # 学院列表（capabilities 在用，保留）
    path("api/organizations/colleges", views.api_college_list, name="college-list"),
    # 组织机构页面
    path("组织机构.html", views.page_org_chart, name="org-chart"),
    # 组织机构（页面 + API）
    path("学生管理.html", views.page_student_list, name="student-list-page"),
    path("班级管理.html", views.page_class_list, name="class-list-page"),
    # 组织机构 API（懒加载树）
    path("api/organizations", views.api_org_list, name="org-list"),
    path("api/organizations/<int:org_id>", views.api_org_detail, name="org-detail"),
    # 班级管理 API
    path("api/classes", views.api_class_list, name="class-list"),
    path("api/classes/graduate", views.api_class_graduate, name="class-graduate"),
    path("api/classes/<int:class_id>", views.api_class_detail, name="class-detail"),
    # 学生管理 API
    path("api/students", views.api_student_list, name="student-list"),
    path("api/students/<int:student_id>", views.api_student_detail, name="student-detail"),
]
