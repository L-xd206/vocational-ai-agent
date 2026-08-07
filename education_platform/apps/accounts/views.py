import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


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
    return JsonResponse({"ok": True, "user": {"name": user.username, "role": "专业负责人"}})


@require_http_methods(["POST"])
def api_logout(request):
    logout(request)
    return JsonResponse({"ok": True})


def api_user_info(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    return JsonResponse({"name": request.user.username, "role": "专业负责人"})
