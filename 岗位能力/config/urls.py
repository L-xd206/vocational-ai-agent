from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from chain.views import page_chain_list, page_user_list, page_role_list

# API
from chain.views import api_chain_list, api_chain_detail, api_chain_create, api_chain_delete, api_job_create, api_job_update, api_job_delete
from crawl.views import api_crawl_start, api_crawl_status
from ability.views import api_ability_generate, api_ability_tree, api_ability_text


def login_view(request):
    """登录页面"""
    return render(request, "login.html")


def index_view(request):
    """主框架（需登录）"""
    if not request.user.is_authenticated:
        return redirect("/login.html")
    return render(request, "index.html")


@csrf_exempt
def api_login(request):
    """登录API"""
    import json
    from django.contrib.auth import authenticate, login
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"error": "仅支持POST"}, status=405)

    data = json.loads(request.body)
    user = authenticate(request, username=data.get("username"), password=data.get("password"))
    if user:
        login(request, user)
        return JsonResponse({"ok": True, "user": {"name": user.username, "role": "专业负责人"}})
    return JsonResponse({"error": "账号或密码错误"}, status=401)


def api_logout(request):
    from django.contrib.auth import logout
    from django.http import JsonResponse
    logout(request)
    return JsonResponse({"ok": True})


def api_user_info(request):
    from django.http import JsonResponse
    if request.user.is_authenticated:
        return JsonResponse({"name": request.user.username, "role": "专业负责人"})
    return JsonResponse({"error": "未登录"}, status=401)


urlpatterns = [
    # 页面
    path("", index_view),
    path("login.html", login_view),
    path("index.html", index_view),
    path("chain-list.html", page_chain_list),       # 能力图谱库（英文别名）
    path("user-list.html", page_user_list),          # 用户管理（英文别名）
    path("role-list.html", page_role_list),          # 角色管理（英文别名）
    path("能力图谱库.html", page_chain_list),
    path("用户管理.html", page_user_list),
    path("角色管理.html", page_role_list),
    path("admin/", admin.site.urls),

    # 登录 API
    path("api/auth/login", api_login),
    path("api/auth/logout", api_logout),
    path("api/auth/me", api_user_info),

    # 产业链 API
    path("api/chain/list", api_chain_list),
    path("api/chain/create", api_chain_create),
    path("api/chain/<int:chain_id>/detail", api_chain_detail),
    path("api/chain/<int:chain_id>/delete", api_chain_delete),
    path("api/job/create", api_job_create),
    path("api/job/<int:job_id>/update", api_job_update),
    path("api/job/<int:job_id>/delete", api_job_delete),

    # 爬虫 API
    path("api/crawl/start", api_crawl_start),
    path("api/crawl/<int:task_id>/status", api_crawl_status),

    # 能力图谱 API
    path("api/ability/generate", api_ability_generate),
    path("api/ability/<int:job_id>/tree", api_ability_tree),
    path("api/ability/<int:job_id>/text", api_ability_text),
]
