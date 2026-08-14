from django.urls import path

from . import views

app_name = "notifications"
urlpatterns = [
    # 页面
    path("通知管理.html", views.page_notice_list, name="notice-list-page"),
    path("系统日志.html", views.page_system_log, name="system-log-page"),
    path("消息通知.html", views.page_my_notifications, name="my-notifications-page"),
    # 通知管理 API
    path("api/notifications", views.api_notification_list, name="notification-list"),
    path("api/notifications/<int:notification_id>", views.api_notification_detail, name="notification-detail"),
    path("api/notifications/<int:notification_id>/status", views.api_notification_status, name="notification-status"),
    # 系统日志 API
    path("api/system-logs", views.api_system_log_list, name="system-log-list"),
    # 消息通知 API
    path("api/my-notifications", views.api_my_notifications, name="my-notifications"),
    path("api/my-notifications/unread-count", views.api_my_unread_count, name="my-notifications-unread-count"),
    path("api/my-notifications/read-all", views.api_my_notifications_read_all, name="my-notifications-read-all"),
    path("api/my-notifications/<int:notification_id>/read", views.api_my_notification_read, name="my-notification-read"),
]
