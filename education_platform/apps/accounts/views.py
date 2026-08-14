import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Permission, Role, UserProfile

User = get_user_model()


def user_to_dict(user):
    """将 User + UserProfile 转为前端字典（共用：列表/me/成员弹窗/profile）"""
    profile = getattr(user, "profile", None)
    role = profile.role if profile else None
    return {
        "id": user.id,
        "username": user.username,
        "real_name": profile.real_name if profile and profile.real_name else user.username,
        "role": {"id": role.id, "name": role.name} if role else None,
        "dept": profile.dept if profile else "",
        "phone": profile.phone if profile else "",
        "email": profile.email if profile else "",
        "avatar": profile.avatar if profile else "",
        "bio": profile.bio if profile else "",
        "is_active": user.is_active,
        "last_login": user.last_login.strftime("%Y-%m-%d %H:%M:%S") if user.last_login else "",
    }


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
    return render(request, "个人中心.html")


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
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_user_create(request)
    # GET：列表（搜索 + 筛选 + 分页）
    keyword = request.GET.get("keyword", "").strip()
    role_id = request.GET.get("role", "").strip()
    status = request.GET.get("status", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)

    queryset = User.objects.select_related("profile__role").all()
    # 搜索：姓名、账号、手机号
    if keyword:
        queryset = queryset.filter(
            Q(username__icontains=keyword)
            | Q(profile__real_name__icontains=keyword)
            | Q(profile__phone__icontains=keyword)
        )
    # 按角色筛选
    if role_id:
        queryset = queryset.filter(profile__role_id=role_id)
    # 按状态筛选
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)

    total = queryset.count()
    offset = (page - 1) * page_size
    users = [user_to_dict(u) for u in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "users": users, "total": total})


def api_user_create(request):
    """新增用户：建账号 + 资料卡，密码默认 edu@123"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    username = data.get("username", "").strip()
    if not username:
        return JsonResponse({"error": "请输入账号"}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({"error": "用户名已存在"}, status=400)
    role_id = data.get("role_id") or None
    if not role_id:
        return JsonResponse({"error": "请选择角色"}, status=400)
    role = Role.objects.filter(pk=role_id).first()
    if role is None:
        return JsonResponse({"error": "角色不存在"}, status=400)
    user = User.objects.create_user(
        username=username,
        password="edu@123",
    )
    UserProfile.objects.create(
        user=user,
        real_name=data.get("real_name", "").strip(),
        dept=data.get("dept", "").strip(),
        phone=data.get("phone", "").strip(),
        email=data.get("email", "").strip(),
        role=role,
    )
    return JsonResponse({"ok": True, "user": user_to_dict(user)}, status=201)


def api_user_detail(request, user_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "DELETE":
        target = User.objects.filter(pk=user_id).first()
        if target is None:
            return JsonResponse({"error": "用户不存在"}, status=404)
        if target.pk == request.user.pk:
            return JsonResponse({"error": "不能删除自己的账号"}, status=400)
        target.delete()
        return JsonResponse({"ok": True})
    # GET：详情
    if request.method == "GET":
        target = User.objects.filter(pk=user_id).select_related("profile__role").first()
        if target is None:
            return JsonResponse({"error": "用户不存在"}, status=404)
        return JsonResponse({"ok": True, "user": user_to_dict(target)})
    # PATCH：编辑
    if request.method != "PATCH":
        return JsonResponse({"error": "不支持的方法"}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    target = User.objects.filter(pk=user_id).select_related("profile").first()
    if target is None:
        return JsonResponse({"error": "用户不存在"}, status=404)
    profile = getattr(target, "profile", None)
    if profile is None:
        return JsonResponse({"error": "该用户无资料卡"}, status=400)
    for field in ["real_name", "dept", "phone", "email"]:
        if field in data:
            setattr(profile, field, data[field].strip() if isinstance(data[field], str) else data[field])
    if "role_id" in data:
        role_id = data["role_id"] or None
        profile.role = Role.objects.filter(pk=role_id).first() if role_id else None
    profile.save()
    return JsonResponse({"ok": True, "user": user_to_dict(target)})


def api_user_status(request, user_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    target = User.objects.filter(pk=user_id).first()
    if target is None:
        return JsonResponse({"error": "用户不存在"}, status=404)
    if "is_active" not in data:
        return JsonResponse({"error": "缺少 is_active 字段"}, status=400)
    target.is_active = bool(data["is_active"])
    target.save()
    return JsonResponse({"ok": True})


def api_permission_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    # 按 module 分组返回
    permissions = Permission.objects.all().order_by("module", "sort_order")
    grouped = {}
    for p in permissions:
        grouped.setdefault(p.module, []).append({"id": p.id, "name": p.name, "code": p.code})
    modules = [{"module": k, "permissions": v} for k, v in grouped.items()]
    return JsonResponse({"ok": True, "modules": modules})


def api_roles(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_role_create(request)
    # GET：列表（搜索 + 分页）
    keyword = request.GET.get("keyword", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    queryset = Role.objects.all()
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    total = queryset.count()
    offset = (page - 1) * page_size
    roles = []
    for role in queryset[offset:offset + page_size]:
        roles.append({
            "id": role.id,
            "name": role.name,
            "description": role.description or "",
            "member_count": role.members.count(),
            "updated_at": role.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "is_builtin": role.is_builtin,
        })
    return JsonResponse({"ok": True, "roles": roles, "total": total})


def api_role_create(request):
    """新增角色"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "请输入角色名称"}, status=400)
    if Role.objects.filter(name=name).exists():
        return JsonResponse({"error": "角色名已存在"}, status=400)
    role = Role.objects.create(
        name=name,
        description=data.get("description", "").strip(),
    )
    if "permission_ids" in data:
        role.permissions.set(data["permission_ids"])
    return JsonResponse({"ok": True, "role": {"id": role.id, "name": role.name}}, status=201)


def api_role_detail(request, role_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "PATCH":
        return api_role_update(request, role_id)
    # GET：单个详情（编辑回填）
    role = Role.objects.filter(pk=role_id).first()
    if role is None:
        return JsonResponse({"error": "角色不存在"}, status=404)
    return JsonResponse({"ok": True, "role": {
        "id": role.id,
        "name": role.name,
        "description": role.description or "",
        "permission_ids": list(role.permissions.values_list("id", flat=True)),
    }})


def api_role_update(request, role_id):
    """编辑角色（没有 DELETE——原型操作列只有编辑/成员）"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    role = Role.objects.filter(pk=role_id).first()
    if role is None:
        return JsonResponse({"error": "角色不存在"}, status=404)
    if "name" in data:
        name = data["name"].strip()
        if name and name != role.name and Role.objects.filter(name=name).exists():
            return JsonResponse({"error": "角色名已存在"}, status=400)
        role.name = name
    if "description" in data:
        role.description = data["description"].strip()
    role.save()
    if "permission_ids" in data:
        role.permissions.set(data["permission_ids"])
    return JsonResponse({"ok": True})


def api_role_members(request, role_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    role = Role.objects.filter(pk=role_id).first()
    if role is None:
        return JsonResponse({"error": "角色不存在"}, status=404)
    members = []
    for profile in role.members.select_related("user").all():
        u = profile.user
        members.append({
            "id": u.id,
            "username": u.username,
            "real_name": profile.real_name or u.username,
            "dept": profile.dept or "",
            "phone": profile.phone or "",
        })
    return JsonResponse({"ok": True, "members": members})


def api_profile(request):
    """我的完整资料（GET）+ 编辑基础资料（PATCH）"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        profile = getattr(request.user, "profile", None)
        if profile is None:
            return JsonResponse({"error": "无资料卡"}, status=400)
        for field in ["real_name", "dept", "phone", "email", "bio"]:
            if field in data:
                setattr(profile, field, data[field].strip() if isinstance(data[field], str) else data[field])
        profile.save()
        return JsonResponse({"ok": True, "profile": user_to_dict(request.user)})
    # GET
    return JsonResponse({"ok": True, "profile": user_to_dict(request.user)})


def api_profile_avatar(request):
    """更换头像（PATCH，body: {avatar: "data:image/..."}）"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    avatar = data.get("avatar", "")
    if not avatar:
        return JsonResponse({"error": "请提供头像数据"}, status=400)
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return JsonResponse({"error": "无资料卡"}, status=400)
    profile.avatar = avatar
    profile.save()
    return JsonResponse({"ok": True})


def api_profile_password(request):
    """修改密码（需短信验证码，假实现 code=123456）"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    code = data.get("code", "").strip()
    if not old_password or not new_password or not code:
        return JsonResponse({"error": "请填写所有必填项"}, status=400)
    if code != "123456":
        return JsonResponse({"error": "验证码错误"}, status=400)
    if not request.user.check_password(old_password):
        return JsonResponse({"error": "原密码错误"}, status=400)
    request.user.set_password(new_password)
    request.user.save()
    return JsonResponse({"ok": True})


def api_profile_phone(request):
    """换绑手机（需短信验证码，假实现 code=123456）"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    code_old = data.get("code_old", "").strip()
    new_phone = data.get("new_phone", "").strip()
    code_new = data.get("code_new", "").strip()
    if not code_old or not new_phone or not code_new:
        return JsonResponse({"error": "请填写所有必填项"}, status=400)
    if code_old != "123456" or code_new != "123456":
        return JsonResponse({"error": "验证码错误"}, status=400)
    import re
    if not re.match(r"^1[3-9]\d{9}$", new_phone):
        return JsonResponse({"error": "手机号格式不正确"}, status=400)
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return JsonResponse({"error": "无资料卡"}, status=400)
    profile.phone = new_phone
    profile.save()
    return JsonResponse({"ok": True})
