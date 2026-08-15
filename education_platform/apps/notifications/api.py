"""notifications 模块对外暴露的接口（跨模块引用统一入口）"""

from django.db.models import Q
from django.utils import timezone

from .models import Notification, NotificationRead, SystemLog


def write_system_log(log_type, content, request=None, user=None, duration_ms=None, detail=None):
    """写系统日志。request 提供时自动取 user/ip（accounts 登录挂钩走这里）。"""
    ip = ""
    if request is not None:
        ip = _get_client_ip(request)
        if user is None and request.user.is_authenticated:
            user = request.user
    return SystemLog.objects.create(
        log_type=log_type,
        content=content,
        user_id=user.id if user is not None else None,
        username=getattr(user, "username", "") or "",
        ip=ip,
        duration_ms=duration_ms,
        detail=detail or {},
    )


def create_notification(title, content, type="system", status="published", publisher=None, audience=None):
    """创建通知（系统事件程序化写入走这里，默认直接已发布）。"""
    notification = Notification(
        title=title,
        content=content,
        type=type,
        status=status,
        publisher=publisher,
        audience=audience,
    )
    if status == Notification.Status.PUBLISHED:
        notification.published_at = timezone.now()
    notification.save()
    return notification


def get_unread_count(user):
    """该用户未读通知数（侧边栏消息角标用）。"""
    read_ids = NotificationRead.objects.filter(user=user).values_list("notification_id", flat=True)
    return get_visible_notifications(user).exclude(id__in=read_ids).count()


def get_visible_notifications(user):
    """面向某用户的已发布通知（audience 匹配：空=所有人，或=用户角色）。"""
    qs = Notification.objects.filter(status=Notification.Status.PUBLISHED)
    role = getattr(getattr(user, "profile", None), "role", None)
    if role:
        qs = qs.filter(Q(audience__isnull=True) | Q(audience=role))
    else:
        qs = qs.filter(audience__isnull=True)
    return qs


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
