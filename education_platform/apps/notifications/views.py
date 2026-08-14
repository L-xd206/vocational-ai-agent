import json

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.api import get_role_by_id

from .api import get_unread_count, get_visible_notifications
from .models import Notification, NotificationRead, SystemLog


def page_notice_list(request):
    return render(request, "通知管理.html")


def page_system_log(request):
    return render(request, "系统日志.html")


def notification_to_dict(n):
    publisher_name = "系统"
    if n.publisher_id:
        profile = getattr(n.publisher, "profile", None)
        publisher_name = profile.real_name if profile and profile.real_name else n.publisher.username
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "type": n.type,
        "type_display": n.get_type_display(),
        "status": n.status,
        "status_display": n.get_status_display(),
        "publisher": publisher_name,
        "published_at": n.published_at.strftime("%Y-%m-%d %H:%M:%S") if n.published_at else "",
        "audience_id": n.audience_id,
        "audience_name": n.audience.name if n.audience else "",
        "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": n.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@csrf_exempt
def api_notification_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_notification_create(request)
    # GET：列表（搜索 + 类型/状态筛选 + 分页）
    keyword = request.GET.get("keyword", "").strip()
    ntype = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    queryset = Notification.objects.select_related("publisher__profile", "audience").all()
    if keyword:
        queryset = queryset.filter(
            Q(title__icontains=keyword)
            | Q(content__icontains=keyword)
            | Q(publisher__username__icontains=keyword)
            | Q(publisher__profile__real_name__icontains=keyword)
        )
    if ntype:
        queryset = queryset.filter(type=ntype)
    if status:
        queryset = queryset.filter(status=status)
    total = queryset.count()
    offset = (page - 1) * page_size
    items = [notification_to_dict(n) for n in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "notifications": items, "total": total})


@csrf_exempt
def api_notification_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    if not title or not content:
        return JsonResponse({"error": "请填写通知标题和内容"}, status=400)
    status = data.get("status", Notification.Status.DRAFT)
    if status not in Notification.Status.values:
        status = Notification.Status.DRAFT
    audience = None
    audience_id = data.get("audience_id") or None
    if audience_id:
        audience = get_role_by_id(audience_id)
        if audience is None:
            return JsonResponse({"error": "受众角色不存在"}, status=400)
    n = Notification(
        title=title,
        content=content,
        type=Notification.Type.SYSTEM,
        status=status,
        publisher=request.user,
        audience=audience,
    )
    if status == Notification.Status.PUBLISHED:
        n.published_at = timezone.now()
    n.save()
    return JsonResponse({"ok": True, "notification": notification_to_dict(n)}, status=201)


@csrf_exempt
def api_notification_detail(request, notification_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    n = Notification.objects.select_related("publisher__profile", "audience").filter(pk=notification_id).first()
    if n is None:
        return JsonResponse({"error": "通知不存在"}, status=404)
    if request.method == "DELETE":
        n.delete()
        return JsonResponse({"ok": True})
    if request.method == "PATCH":
        # 已发布不可编辑，需先下架
        if n.status == Notification.Status.PUBLISHED:
            return JsonResponse({"error": "已发布通知不可编辑，请先下架"}, status=400)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        if "title" in data:
            n.title = data["title"].strip()
        if "content" in data:
            n.content = data["content"].strip()
        if "audience_id" in data:
            audience_id = data["audience_id"] or None
            if audience_id:
                audience = get_role_by_id(audience_id)
                if audience is None:
                    return JsonResponse({"error": "受众角色不存在"}, status=400)
                n.audience = audience
            else:
                n.audience = None
        if not n.title or not n.content:
            return JsonResponse({"error": "请填写通知标题和内容"}, status=400)
        n.save()
        return JsonResponse({"ok": True, "notification": notification_to_dict(n)})
    return JsonResponse({"error": "不支持的方法"}, status=405)


@csrf_exempt
def api_notification_status(request, notification_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    n = Notification.objects.select_related("publisher__profile", "audience").filter(pk=notification_id).first()
    if n is None:
        return JsonResponse({"error": "通知不存在"}, status=404)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    new_status = data.get("status")
    if new_status == Notification.Status.PUBLISHED:
        if n.status not in (Notification.Status.DRAFT, Notification.Status.OFFLINE):
            return JsonResponse({"error": "当前状态不能发布"}, status=400)
        n.status = Notification.Status.PUBLISHED
        if not n.published_at:
            n.published_at = timezone.now()
    elif new_status == Notification.Status.OFFLINE:
        if n.status != Notification.Status.PUBLISHED:
            return JsonResponse({"error": "只有已发布的通知才能下架"}, status=400)
        n.status = Notification.Status.OFFLINE
    else:
        return JsonResponse({"error": "无效的状态"}, status=400)
    n.save()
    return JsonResponse({"ok": True, "notification": notification_to_dict(n)})


# ===== 系统日志 =====

def log_to_dict(l):
    return {
        "id": l.id,
        "content": l.content,
        "user_id": l.user_id,
        "username": l.username or "",
        "ip": l.ip or "",
        "duration_ms": l.duration_ms,
        "log_type": l.log_type,
        "log_type_display": l.get_log_type_display(),
        "detail": l.detail or {},
        "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@csrf_exempt
def api_system_log_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    log_type = request.GET.get("log_type", "").strip()
    keyword = request.GET.get("keyword", "").strip()
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    queryset = SystemLog.objects.all()
    if log_type:
        queryset = queryset.filter(log_type=log_type)
    if keyword:
        queryset = queryset.filter(
            Q(content__icontains=keyword) | Q(username__icontains=keyword) | Q(ip__icontains=keyword)
        )
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    total = queryset.count()
    offset = (page - 1) * page_size
    items = [log_to_dict(l) for l in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "logs": items, "total": total})


# ===== 消息通知 =====

def my_notification_to_dict(n, is_read):
    return {
        "id": n.id,
        "title": n.title,
        "content": n.content,
        "type": n.type,
        "type_display": n.get_type_display(),
        "published_at": n.published_at.strftime("%Y-%m-%d %H:%M:%S") if n.published_at else "",
        "is_read": is_read,
    }


def page_my_notifications(request):
    return render(request, "消息通知.html")


@csrf_exempt
def api_my_notifications(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    visible = get_visible_notifications(request.user).order_by("-published_at", "-id")
    read_ids = set(NotificationRead.objects.filter(user=request.user).values_list("notification_id", flat=True))
    unread_count = sum(1 for nid in visible.values_list("id", flat=True) if nid not in read_ids)
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    total = visible.count()
    offset = (page - 1) * page_size
    items = [my_notification_to_dict(n, n.id in read_ids) for n in visible[offset:offset + page_size]]
    return JsonResponse({"ok": True, "notifications": items, "total": total, "unread_count": unread_count})


@csrf_exempt
def api_my_unread_count(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    return JsonResponse({"ok": True, "unread_count": get_unread_count(request.user)})


@csrf_exempt
def api_my_notification_read(request, notification_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    n = get_visible_notifications(request.user).filter(pk=notification_id).first()
    if n is None:
        return JsonResponse({"error": "通知不存在"}, status=404)
    NotificationRead.objects.get_or_create(user=request.user, notification=n)
    return JsonResponse({"ok": True})


@csrf_exempt
def api_my_notifications_read_all(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    read_ids = set(NotificationRead.objects.filter(user=request.user).values_list("notification_id", flat=True))
    for n in get_visible_notifications(request.user).exclude(id__in=read_ids):
        NotificationRead.objects.get_or_create(user=request.user, notification=n)
    return JsonResponse({"ok": True})
