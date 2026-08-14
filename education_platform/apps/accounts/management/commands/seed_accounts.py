"""预置权限点、内置角色与 admin 账号（幂等，可重复执行）

用法：python manage.py seed_accounts
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission, Role, UserProfile

# 18 个权限点：module=所属模块, name=页面名, code=权限码, url=页面路径
PERMISSIONS = [
    {"module": "岗位采集", "name": "岗位数据采集", "code": "job_collection", "url": "岗位数据采集.html"},
    {"module": "岗位采集", "name": "未采纳数据", "code": "rejected_data", "url": "未采纳数据.html"},
    {"module": "能力图谱", "name": "能力图谱库", "code": "capability_graph", "url": "能力图谱库.html"},
    {"module": "教师工作台", "name": "课程管理", "code": "course_manage", "url": "课程管理.html"},
    {"module": "教师工作台", "name": "教育资源库", "code": "resource_library", "url": "教育资源库.html"},
    {"module": "教师工作台", "name": "教学安排", "code": "teaching_schedule", "url": "教学安排.html"},
    {"module": "教师工作台", "name": "试题库", "code": "question_bank", "url": "试题库.html"},
    {"module": "学习空间", "name": "学习计划", "code": "learning_plan", "url": "学习计划.html"},
    {"module": "学习空间", "name": "学习档案", "code": "learning_archive", "url": "学习档案.html"},
    {"module": "系统管理", "name": "通知管理", "code": "notification", "url": "通知管理.html"},
    {"module": "系统管理", "name": "组织机构", "code": "organization", "url": "组织机构.html"},
    {"module": "系统管理", "name": "用户管理", "code": "user_manage", "url": "用户管理.html"},
    {"module": "系统管理", "name": "班级管理", "code": "class_manage", "url": "班级管理.html"},
    {"module": "系统管理", "name": "学生管理", "code": "student_manage", "url": "学生管理.html"},
    {"module": "系统管理", "name": "角色管理", "code": "role_manage", "url": "角色管理.html"},
    {"module": "系统管理", "name": "系统日志", "code": "system_log", "url": "系统日志.html"},
    {"module": "个人", "name": "个人中心", "code": "profile", "url": "个人中心.html"},
    {"module": "系统管理", "name": "消息通知", "code": "message", "url": "消息通知.html"},
]


class Command(BaseCommand):
    help = "预置权限点、角色与测试账号（幂等，可重复执行）"

    def handle(self, *args, **options):
        self.seed_permissions()
        self.seed_roles_and_admin()
        self.seed_standard_roles()
        self.seed_test_users()
        self.stdout.write(self.style.SUCCESS(
            f"seed 完成：权限点 {Permission.objects.count()} 条"
        ))

    def seed_permissions(self):
        """预置 18 个权限点（幂等：重复跑不重复插，已存在的会更新 module/name/url）"""
        with transaction.atomic():
            for item in PERMISSIONS:
                perm, created = Permission.objects.get_or_create(code=item["code"], defaults=item)
                if not created:
                    # 已存在的权限点，用最新值覆盖（如搬家：消息通知从"个人"移到"系统管理"）
                    changed = False
                    for field in ["module", "name", "url"]:
                        if getattr(perm, field) != item[field]:
                            setattr(perm, field, item[field])
                            changed = True
                    if changed:
                        perm.save()

    def seed_roles_and_admin(self):
        """内置角色 + admin 账号（三态：无号建号建卡 / 有号无卡补卡 / 都全跳过）"""
        User = get_user_model()
        with transaction.atomic():
            # 1. 内置角色"超级管理员"，挂全部权限
            admin_role, _ = Role.objects.get_or_create(
                name="超级管理员",
                defaults={"description": "拥有全部权限", "is_builtin": True},
            )
            admin_role.permissions.set(Permission.objects.all())

            # 2. admin 账号（超级管理员，能进 Django 后台）
            admin_user = User.objects.filter(username="admin").first()
            if admin_user is None:
                # 情况一：账号不存在 → 建号 + 建卡
                admin_user = User.objects.create_user(username="admin", password="admin123")
                admin_user.is_staff = True       # Django 后台访问权限
                admin_user.is_superuser = True   # 所有权限（后台不受限制）
                admin_user.save()
                UserProfile.objects.create(user=admin_user, real_name="管理员", role=admin_role)
                self.stdout.write("已创建 admin 账号及资料卡")
            else:
                # 账号存在：补 is_staff / is_superuser（幂等：如果已有跳过）
                if not admin_user.is_staff or not admin_user.is_superuser:
                    admin_user.is_staff = True
                    admin_user.is_superuser = True
                    admin_user.save()
                    self.stdout.write("已为 admin 补上 staff/superuser 标记")
                # 补资料卡
                if not hasattr(admin_user, "profile"):
                    UserProfile.objects.create(user=admin_user, real_name="管理员", role=admin_role)
                    self.stdout.write("已为 admin 补建资料卡")
                else:
                    self.stdout.write("admin 已完整，跳过")

    def seed_standard_roles(self):
        """预置常用角色（教师、学生），各挂合理权限"""
        # 教师：教师工作台 + 学习空间 + 个人
        teacher_permissions = Permission.objects.filter(code__in=[
            "course_manage", "resource_library", "teaching_schedule", "question_bank",
            "learning_plan", "learning_archive",
            "profile", "message",
        ])
        teacher_role, created = Role.objects.get_or_create(
            name="教师",
            defaults={"description": "维护课程、能力项与实训资源", "is_builtin": False},
        )
        if created:
            teacher_role.permissions.set(teacher_permissions)
            self.stdout.write("已创建角色：教师")
        else:
            self.stdout.write("角色 教师 已存在，跳过")

        # 学生：学习空间 + 个人
        student_permissions = Permission.objects.filter(code__in=[
            "learning_plan", "learning_archive",
            "profile", "message",
        ])
        student_role, created = Role.objects.get_or_create(
            name="学生",
            defaults={"description": "查看学习计划与个人档案", "is_builtin": False},
        )
        if created:
            student_role.permissions.set(student_permissions)
            self.stdout.write("已创建角色：学生")
        else:
            self.stdout.write("角色 学生 已存在，跳过")

    def seed_test_users(self):
        """预置测试用户：一名教师、一名学生，资料完整（幂等）"""
        User = get_user_model()
        teacher_role = Role.objects.filter(name="教师").first()
        student_role = Role.objects.filter(name="学生").first()
        if not teacher_role or not student_role:
            self.stdout.write("⚠ 教师/学生 角色缺失，跳过测试用户")
            return

        test_accounts = [
            {
                "username": "teacher",
                "password": "edu@123",
                "real_name": "李思雨",
                "role": teacher_role,
                "dept": "智能制造学院",
                "phone": "13800001234",
                "email": "teacher@edu.com",
                "bio": "负责智能制造专业课程教学与实训指导",
            },
            {
                "username": "student",
                "password": "edu@123",
                "real_name": "张同学",
                "role": student_role,
                "dept": "智能制造学院",
                "phone": "13900005678",
                "email": "student@edu.com",
                "bio": "智能制造专业2025级学生",
            },
        ]

        for item in test_accounts:
            user = User.objects.filter(username=item["username"]).first()
            if user is None:
                user = User.objects.create_user(
                    username=item["username"],
                    password=item["password"],
                )
                UserProfile.objects.create(
                    user=user,
                    real_name=item["real_name"],
                    role=item["role"],
                    dept=item["dept"],
                    phone=item["phone"],
                    email=item["email"],
                    bio=item["bio"],
                )
                self.stdout.write(f"已创建测试用户：{item['username']}")
            elif not hasattr(user, "profile"):
                UserProfile.objects.create(
                    user=user,
                    real_name=item["real_name"],
                    role=item["role"],
                    dept=item["dept"],
                    phone=item["phone"],
                    email=item["email"],
                    bio=item["bio"],
                )
                self.stdout.write(f"已为 {item['username']} 补建资料卡")
            else:
                self.stdout.write(f"用户 {item['username']} 已完整，跳过")
