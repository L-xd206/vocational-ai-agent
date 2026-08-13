import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from django.db.models import Q

from .models import Class, College, Organization, Student


def page_org_chart(request):
    return render(request, "组织机构.html")


def page_class_list(request):
    return render(request, "班级管理.html")


def page_student_list(request):
    return render(request, "学生管理.html")


def api_college_list(request):
    colleges = College.objects.filter(is_enabled=True).values("id", "name")
    return JsonResponse({"colleges": list(colleges)})


def org_to_dict(org):
    """Organization → 前端字典"""
    return {
        "id": org.id,
        "name": org.name,
        "org_type": org.org_type,
        "parent_id": org.parent_id,
        "leader": org.leader or "",
        "description": org.description or "",
        "has_children": org.children.exists(),
        "is_enabled": org.is_enabled,
        "created_at": org.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@csrf_exempt
def api_org_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_org_create(request)
    # GET：树 / 子节点 / 平铺
    flat = request.GET.get("flat") == "1"
    if flat:
        orgs = Organization.objects.filter(is_enabled=True).order_by("sort_order", "id")
        return JsonResponse({"ok": True, "items": [org_to_dict(o) for o in orgs]})
    parent_id = request.GET.get("parent_id")
    if parent_id:
        orgs = Organization.objects.filter(parent_id=parent_id, is_enabled=True).order_by("sort_order", "id")
    else:
        orgs = Organization.objects.filter(parent__isnull=True, is_enabled=True).order_by("sort_order", "id")
    return JsonResponse({"ok": True, "items": [org_to_dict(o) for o in orgs]})


@csrf_exempt
def api_org_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    name = data.get("name", "").strip()
    org_type = data.get("org_type", "").strip()
    if not name or not org_type:
        return JsonResponse({"error": "请填写机构名称和类型"}, status=400)
    parent_id = data.get("parent_id") or None
    parent = Organization.objects.filter(pk=parent_id).first() if parent_id else None
    org = Organization.objects.create(
        name=name,
        org_type=org_type,
        parent=parent,
        leader=data.get("leader", "").strip(),
        description=data.get("description", "").strip(),
    )
    return JsonResponse({"ok": True, "org": org_to_dict(org)}, status=201)


@csrf_exempt
def api_org_detail(request, org_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "PATCH":
        return api_org_update(request, org_id)
    if request.method == "DELETE":
        org = Organization.objects.filter(pk=org_id).first()
        if org is None:
            return JsonResponse({"error": "机构不存在"}, status=404)
        if org.children.exists():
            return JsonResponse({"error": "该机构下还有子机构，请先删除子机构"}, status=400)
        org.delete()
        return JsonResponse({"ok": True})
    # GET：详情
    org = Organization.objects.filter(pk=org_id).first()
    if org is None:
        return JsonResponse({"error": "机构不存在"}, status=404)
    return JsonResponse({"ok": True, "org": org_to_dict(org)})


@csrf_exempt
def api_org_update(request, org_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    org = Organization.objects.filter(pk=org_id).first()
    if org is None:
        return JsonResponse({"error": "机构不存在"}, status=404)
    for field in ["name", "org_type", "leader", "description"]:
        if field in data:
            setattr(org, field, data[field].strip() if isinstance(data[field], str) else data[field])
    if "parent_id" in data:
        parent_id = data["parent_id"] or None
        new_parent = Organization.objects.filter(pk=parent_id).first() if parent_id else None
        if new_parent is not None:
            if new_parent.pk == org.pk:
                return JsonResponse({"error": "不能将自己设为上级机构"}, status=400)
            # 检测循环引用：从新 parent 往上爬，看是否会回到自己
            ancestor = new_parent.parent
            while ancestor is not None:
                if ancestor.pk == org.pk:
                    return JsonResponse({"error": "不能形成循环引用"}, status=400)
                ancestor = ancestor.parent
        org.parent = new_parent
    org.save()
    return JsonResponse({"ok": True, "org": org_to_dict(org)})


# ===== 班级管理 =====

def class_to_dict(cls):
    return {
        "id": cls.id,
        "name": cls.name,
        "code": cls.code,
        "org_id": cls.org_id,
        "org_name": cls.org.name if cls.org else "",
        "major": cls.major or "",
        "grade": cls.grade or "",
        "teacher": cls.teacher or "",
        "status": cls.status,
        "student_count": cls.students.count(),
        "created_at": cls.created_at.strftime("%Y-%m-%d"),
    }


@csrf_exempt
def api_class_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_class_create(request)
    # GET：列表（搜索 + 筛选 + 分页）
    keyword = request.GET.get("keyword", "").strip()
    major = request.GET.get("major", "").strip()
    grade = request.GET.get("grade", "").strip()
    status = request.GET.get("status", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    queryset = Class.objects.select_related("org").all()
    if keyword:
        queryset = queryset.filter(Q(name__icontains=keyword) | Q(code__icontains=keyword) | Q(teacher__icontains=keyword))
    if major:
        queryset = queryset.filter(major=major)
    if grade:
        queryset = queryset.filter(grade=grade)
    if status:
        queryset = queryset.filter(status=status)
    total = queryset.count()
    offset = (page - 1) * page_size
    items = [class_to_dict(c) for c in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "classes": items, "total": total})


@csrf_exempt
def api_class_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    name = data.get("name", "").strip()
    code = data.get("code", "").strip()
    if not name or not code:
        return JsonResponse({"error": "请填写班级名称和编号"}, status=400)
    if Class.objects.filter(code=code).exists():
        return JsonResponse({"error": "班级编号已存在"}, status=400)
    major = data.get("major", "").strip()
    if not major:
        return JsonResponse({"error": "请选择专业"}, status=400)
    # 根据专业名找机构节点（org_type=专业）
    org = Organization.objects.filter(name=major, org_type="专业").first()
    cls = Class.objects.create(
        name=name, code=code, org=org,
        major=major,
        grade=data.get("grade", "").strip(),
        teacher=data.get("teacher", "").strip(),
    )
    return JsonResponse({"ok": True, "class": class_to_dict(cls)}, status=201)


@csrf_exempt
def api_class_detail(request, class_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    cls = Class.objects.filter(pk=class_id).first()
    if cls is None:
        return JsonResponse({"error": "班级不存在"}, status=404)
    if request.method == "DELETE":
        cls.delete()
        return JsonResponse({"ok": True})
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        for field in ["name", "grade", "teacher", "status"]:
            if field in data:
                setattr(cls, field, data[field].strip() if isinstance(data[field], str) else data[field])
        if "major" in data:
            major = data["major"].strip()
            if major:
                cls.org = Organization.objects.filter(name=major, org_type="专业").first()
                cls.major = major
        if "code" in data and data["code"].strip() != cls.code:
            new_code = data["code"].strip()
            if Class.objects.filter(code=new_code).exists():
                return JsonResponse({"error": "班级编号已存在"}, status=400)
            cls.code = new_code
        cls.save()
        return JsonResponse({"ok": True, "class": class_to_dict(cls)})
    # GET：详情
    return JsonResponse({"ok": True, "class": class_to_dict(cls)})


@csrf_exempt
def api_class_graduate(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    ids = data.get("ids", [])
    if not ids:
        return JsonResponse({"error": "请选择班级"}, status=400)
    count = Class.objects.filter(pk__in=ids).exclude(status="graduated").update(status="graduated")
    return JsonResponse({"ok": True, "graduated": count})


# ===== 学生管理 =====

def student_to_dict(s):
    return {
        "id": s.id,
        "name": s.name,
        "student_id": s.student_id,
        "major": s.major or "",
        "grade": s.grade or "",
        "class_group_id": s.class_group_id,
        "class_name": s.class_group.name if s.class_group else "",
        "phone": s.phone or "",
        "last_login": s.user.last_login.strftime("%Y-%m-%d %H:%M:%S") if s.user and s.user.last_login else "",
        "created_at": s.created_at.strftime("%Y-%m-%d"),
    }


@csrf_exempt
def api_student_list(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    if request.method == "POST":
        return api_student_create(request)
    # GET：列表（搜索 + 筛选 + 分页）
    keyword = request.GET.get("keyword", "").strip()
    major = request.GET.get("major", "").strip()
    grade = request.GET.get("grade", "").strip()
    class_id = request.GET.get("class_group_id", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = int(request.GET.get("page_size", 10) or 10)
    queryset = Student.objects.select_related("class_group", "user").all()
    if keyword:
        queryset = queryset.filter(
            Q(name__icontains=keyword) | Q(student_id__icontains=keyword) | Q(phone__icontains=keyword)
        )
    if major:
        queryset = queryset.filter(major=major)
    if grade:
        queryset = queryset.filter(grade=grade)
    if class_id:
        queryset = queryset.filter(class_group_id=class_id)
    total = queryset.count()
    offset = (page - 1) * page_size
    items = [student_to_dict(s) for s in queryset[offset:offset + page_size]]
    return JsonResponse({"ok": True, "students": items, "total": total})


@csrf_exempt
def api_student_create(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "无效的 JSON"}, status=400)
    name = data.get("name", "").strip()
    student_id = data.get("student_id", "").strip()
    if not name or not student_id:
        return JsonResponse({"error": "请填写姓名和学号"}, status=400)
    if Student.objects.filter(student_id=student_id).exists():
        return JsonResponse({"error": "学号已存在"}, status=400)
    class_id = data.get("class_group_id") or None
    cls = Class.objects.filter(pk=class_id).first() if class_id else None
    # 有班级则从班级同步 major/grade，忽略前端传值
    s = Student.objects.create(
        name=name, student_id=student_id,
        major=cls.major if cls else "",
        grade=cls.grade if cls else "",
        class_group=cls,
        phone=data.get("phone", "").strip(),
    )
    return JsonResponse({"ok": True, "student": student_to_dict(s)}, status=201)


@csrf_exempt
def api_student_detail(request, student_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "未登录"}, status=401)
    s = Student.objects.filter(pk=student_id).first()
    if s is None:
        return JsonResponse({"error": "学生不存在"}, status=404)
    if request.method == "DELETE":
        s.delete()
        return JsonResponse({"ok": True})
    if request.method == "PATCH":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "无效的 JSON"}, status=400)
        for field in ["name", "phone"]:
            if field in data:
                setattr(s, field, data[field].strip() if isinstance(data[field], str) else data[field])
        if "class_group_id" in data:
            cid = data["class_group_id"] or None
            s.class_group = Class.objects.filter(pk=cid).first() if cid else None
            if s.class_group:
                s.major = s.class_group.major
                s.grade = s.class_group.grade
        if "student_id" in data and data["student_id"].strip() != s.student_id:
            new_id = data["student_id"].strip()
            if Student.objects.filter(student_id=new_id).exists():
                return JsonResponse({"error": "学号已存在"}, status=400)
            s.student_id = new_id
        s.save()
        return JsonResponse({"ok": True, "student": student_to_dict(s)})
    # GET：详情
    return JsonResponse({"ok": True, "student": student_to_dict(s)})
