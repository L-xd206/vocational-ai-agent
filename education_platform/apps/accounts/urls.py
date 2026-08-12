from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # ---- 页面路由 ----
    path("login.html", views.login_view, name="login"),
    path("用户管理.html", views.page_user_list, name="user-list"),
    path("角色管理.html", views.page_role_list, name="role-list"),
    path("个人中心.html", views.page_profile, name="profile"),

    # ---- auth 认证 ----
    path("api/auth/login", views.api_login, name="api-login"),
    path("api/auth/logout", views.api_logout, name="api-logout"),
    path("api/auth/me", views.api_user_info, name="api-user-info"),
    path("api/auth/forgot-password/send", views.api_forgot_send, name="api-forgot-send"),
    path("api/auth/forgot-password/reset", views.api_forgot_reset, name="api-forgot-reset"),

    # ---- users 用户管理 ----
    path("api/users", views.api_users, name="api-user-list"),
    path("api/users/<int:user_id>", views.api_user_detail, name="api-user-detail"),
    path("api/users/<int:user_id>/status", views.api_user_status, name="api-user-status"),

    # ---- roles 角色管理 ----
    path("api/permissions", views.api_permission_list, name="api-permission-list"),
    path("api/roles", views.api_roles, name="api-role-list"),
    path("api/roles/<int:role_id>", views.api_role_detail, name="api-role-detail"),
    path("api/roles/<int:role_id>/members", views.api_role_members, name="api-role-members"),

    # ---- profile 个人中心 ----
    path("api/profile", views.api_profile, name="api-profile"),
    path("api/profile/avatar", views.api_profile_avatar, name="api-profile-avatar"),
    path("api/profile/password", views.api_profile_password, name="api-profile-password"),
    path("api/profile/phone", views.api_profile_phone, name="api-profile-phone"),
]
