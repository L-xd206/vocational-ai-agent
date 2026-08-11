import json

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import UserProfile


def login_view(request):
    return render(request, "login.html")


def page_user_list(request):
    return render(request, "用户管理.html")


def page_role_list(request):
    return render(request, "角色管理.html")


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    user = authenticate(request, username=data.get("username"), password=data.get("password"))
    if not user:
        return JsonResponse({"error": "账号或密码错误"}, status=401)
    login(request, user)
    # 身份信息不在这里返回，前端跳转后调 /api/auth/me 获取（避免重复序列化）
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
def api_logout(request):
    logout(request)
    return JsonResponse({"ok": True})


def api_user_info(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    user = request.user
    profile = getattr(user, "profile", None)  # 没有资料卡时返回 None，不报错
    role = profile.role if profile else None
    return JsonResponse({"ok": True, "user": {
        "id": user.id,
        "username": user.username,
        "real_name": profile.real_name if profile and profile.real_name else user.username,
        "role": {"id": role.id, "name": role.name} if role else None,
        "avatar": profile.avatar if profile else "",
        "permissions": role.permission_codes if role else [],
    }})


# ===== 以下为新接口的空壳（占位，逐步填充）=====

def page_profile(request):
    return HttpResponse("个人中心（待实现）")


@csrf_exempt
@require_http_methods(["POST"])
def api_forgot_send(request):
    """忘记密码第一步：按手机号发验证码（假实现，验证码固定 123456）"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    phone = data.get("phone", "").strip()
    if not phone:
        return JsonResponse({"error": "请输入手机号"}, status=400)
    profile = UserProfile.objects.filter(phone=phone).select_related("user").first()
    if profile is None:
        return JsonResponse({"error": "该手机号未绑定账号"}, status=400)
    return JsonResponse({"ok": True, "message": "验证码已发送"})


@csrf_exempt
@require_http_methods(["POST"])
def api_forgot_reset(request):
    """忘记密码第二步：校验验证码并设新密码"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    phone = data.get("phone", "").strip()
    code = data.get("code", "").strip()
    new_password = data.get("new_password", "")
    if not phone or not code or not new_password:
        return JsonResponse({"error": "请填写手机号、验证码和新密码"}, status=400)
    if code != "123456":
        return JsonResponse({"error": "验证码错误"}, status=400)
    profile = UserProfile.objects.filter(phone=phone).select_related("user").first()
    if profile is None:
        return JsonResponse({"error": "该手机号未绑定账号"}, status=400)
    profile.user.set_password(new_password)
    profile.user.save()
    return JsonResponse({"ok": True})


def api_users(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_user_detail(request, user_id):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_user_status(request, user_id):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_permission_list(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_roles(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_role_detail(request, role_id):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_role_members(request, role_id):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_profile(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_profile_avatar(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_profile_password(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)


def api_profile_phone(request):
    return JsonResponse({"ok": False, "error": "开发中"}, status=501)
