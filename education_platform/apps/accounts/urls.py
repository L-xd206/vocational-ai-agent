from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login.html", views.login_view, name="login"),
    path("api/auth/login", views.api_login, name="api-login"),
    path("api/auth/logout", views.api_logout, name="api-logout"),
    path("api/auth/me", views.api_user_info, name="api-user-info"),
    path("user-list.html", views.page_user_list, name="user-list"),
    path("role-list.html", views.page_role_list, name="role-list"),
    path("用户管理.html", views.page_user_list, name="user-list-cn"),
    path("角色管理.html", views.page_role_list, name="role-list-cn"),
]
