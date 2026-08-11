import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import Client

from .models import Permission, Role, UserProfile

User = get_user_model()


class AuthTest(TestCase):
    """登录 / 登出 / me / 忘记密码"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="admin", password="admin123")
        cls.admin.is_staff = True
        cls.admin.save()
        role = Role.objects.create(name="管理员")
        UserProfile.objects.create(user=cls.admin, real_name="管理员", phone="13800000001", role=role)

    def test_login_ok(self):
        c = Client()
        r = c.post("/api/auth/login", data=json.dumps({"username": "admin", "password": "admin123"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])

    def test_login_bad_password(self):
        c = Client()
        r = c.post("/api/auth/login", data=json.dumps({"username": "admin", "password": "wrong"}), content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_me_unauthenticated(self):
        c = Client()
        r = c.get("/api/auth/me")
        self.assertEqual(r.status_code, 401)

    def test_me_authenticated(self):
        c = Client()
        c.login(username="admin", password="admin123")
        r = c.get("/api/auth/me")
        self.assertEqual(r.status_code, 200)
        user = r.json()["user"]
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["real_name"], "管理员")

    def test_forgot_send_bound(self):
        c = Client()
        r = c.post("/api/auth/forgot-password/send", data=json.dumps({"phone": "13800000001"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_forgot_send_unbound(self):
        c = Client()
        r = c.post("/api/auth/forgot-password/send", data=json.dumps({"phone": "19900000000"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_forgot_reset_wrong_code(self):
        c = Client()
        r = c.post("/api/auth/forgot-password/reset", data=json.dumps({"phone": "13800000001", "code": "000000", "new_password": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_forgot_reset_ok(self):
        c = Client()
        r = c.post("/api/auth/forgot-password/reset", data=json.dumps({"phone": "13800000001", "code": "123456", "new_password": "newpass"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 新密码能登录
        ok = c.login(username="admin", password="newpass")
        self.assertTrue(ok)


class UsersTest(TestCase):
    """用户管理：列表 / 新增 / 搜索 / 筛选 / 分页"""

    @classmethod
    def setUpTestData(cls):
        cls.role_a = Role.objects.create(name="教师")
        cls.role_b = Role.objects.create(name="学生")
        u1 = User.objects.create_user(username="teacher01", password="edu@123")
        UserProfile.objects.create(user=u1, real_name="李思雨", phone="13800001234", dept="智能制造学院", role=cls.role_a)
        u2 = User.objects.create_user(username="student01", password="edu@123")
        UserProfile.objects.create(user=u2, real_name="张同学", phone="13900005678", dept="智能制造学院", role=cls.role_b)
        # 第三个：无资料卡的用户（边界 case）
        User.objects.create_user(username="no_profile", password="edu@123")

    def setUp(self):
        self.c = Client()
        self.c.login(username="teacher01", password="edu@123")

    def test_list_all(self):
        r = self.c.get("/api/users")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreaterEqual(d["total"], 3)

    def test_search_keyword(self):
        r = self.c.get("/api/users?keyword=李")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["real_name"], "李思雨")

    def test_search_by_phone(self):
        r = self.c.get("/api/users?keyword=13900005678")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["username"], "student01")

    def test_filter_role(self):
        r = self.c.get(f"/api/users?role={self.role_a.id}")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["role"]["name"], "教师")

    def test_filter_status(self):
        r = self.c.get("/api/users?status=active")
        d = r.json()
        for u in d["users"]:
            self.assertTrue(u["is_active"])

    def test_pagination(self):
        r = self.c.get("/api/users?page=1&page_size=2")
        d = r.json()
        self.assertEqual(len(d["users"]), 2)
        self.assertGreaterEqual(d["total"], 3)

    def test_create_ok(self):
        r = self.c.post("/api/users", data=json.dumps({
            "username": "newuser",
            "real_name": "新用户",
            "role_id": self.role_a.id,
            "dept": "测试部",
            "phone": "13000000000",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["user"]["username"], "newuser")
        # 默认密码能登录
        ok = self.c.login(username="newuser", password="edu@123")
        self.assertTrue(ok)

    def test_create_duplicate(self):
        r = self.c.post("/api/users", data=json.dumps({"username": "teacher01", "real_name": "重复"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("已存在", r.json()["error"])

    def test_no_profile_user(self):
        """无资料卡的用户兜底：real_name 退回 username，不崩溃"""
        r = self.c.get("/api/users?keyword=no_profile")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["real_name"], "no_profile")

    # ---- 编辑 / 停用 / 删除 ----

    def test_edit_ok(self):
        target = User.objects.get(username="teacher01")
        r = self.c.patch(f"/api/users/{target.pk}", data=json.dumps({
            "real_name": "李思雨改",
            "dept": "新部门",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["real_name"], "李思雨改")
        # 数据库也改了
        target.refresh_from_db()
        self.assertEqual(target.profile.real_name, "李思雨改")

    def test_edit_not_found(self):
        r = self.c.patch("/api/users/99999", data=json.dumps({"real_name": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_status_toggle(self):
        target = User.objects.get(username="student01")
        r = self.c.patch(f"/api/users/{target.pk}/status", data=json.dumps({"is_active": False}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        # 启用回来
        self.c.patch(f"/api/users/{target.pk}/status", data=json.dumps({"is_active": True}), content_type="application/json")
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_delete_ok(self):
        target = User.objects.get(username="student01")
        r = self.c.delete(f"/api/users/{target.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="student01").exists())

    def test_delete_self(self):
        """不能删自己"""
        me = User.objects.get(username="teacher01")
        r = self.c.delete(f"/api/users/{me.pk}")
        self.assertEqual(r.status_code, 400)
        self.assertIn("自己", r.json()["error"])


class UserJourneyTest(TestCase):
    """模拟真实用户操作流程：登录 → 忘记密码 → 用户增删改查"""

    @classmethod
    def setUpTestData(cls):
        cls.role = Role.objects.create(name="管理员")
        cls.admin_user = User.objects.create_user(username="admin", password="admin123")
        cls.admin_user.is_staff = True
        cls.admin_user.save()
        UserProfile.objects.create(user=cls.admin_user, real_name="管理员", phone="13800000001", role=cls.role)

    def setUp(self):
        self.c = Client()

    # ===== 流程 1：登录 → 看身份 =====

    def test_journey_login_and_me(self):
        """用户打开登录页 → 输账号密码 → 登录成功 → 跳转首页 → 顶部显示用户名和角色"""
        # 1. 登录
        r = self.c.post("/api/auth/login", data=json.dumps({
            "username": "admin", "password": "admin123",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        # 2. 加载全局框架（/me 是每个页面顶部都会调的）
        r = self.c.get("/api/auth/me")
        d = r.json()
        self.assertEqual(d["user"]["username"], "admin")
        self.assertEqual(d["user"]["real_name"], "管理员")
        self.assertEqual(d["user"]["role"]["name"], "管理员")

    # ===== 流程 2：忘记密码 → 重置 → 用新密码登录 =====

    def test_journey_forgot_password(self):
        """用户在登录页点"忘记密码" → 输手机号 → 收验证码 → 设新密码 → 用新密码登进去"""
        # 1. 输入手机号，获取验证码
        r = self.c.post("/api/auth/forgot-password/send", data=json.dumps({
            "phone": "13800000001",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 2. 填验证码 + 新密码，确认重置
        r = self.c.post("/api/auth/forgot-password/reset", data=json.dumps({
            "phone": "13800000001", "code": "123456", "new_password": "mynewpass",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 3. 用新密码登录 → 成功
        r = self.c.post("/api/auth/login", data=json.dumps({
            "username": "admin", "password": "mynewpass",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 4. 旧密码登不上
        r = self.c.post("/api/auth/login", data=json.dumps({
            "username": "admin", "password": "admin123",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 401)

    # ===== 流程 3：用户管理全流程 =====

    def test_journey_user_crud(self):
        """管理员登录 → 打开用户列表 → 搜索 → 新增用户 → 编辑 → 停用 → 删除"""
        self.c.login(username="admin", password="admin123")

        # 1. 打开用户列表，能看到已有的用户
        r = self.c.get("/api/users")
        d = r.json()
        self.assertGreaterEqual(d["total"], 1)

        # 2. 搜索一个不存在的用户 → 空列表
        r = self.c.get("/api/users?keyword=不存在的名字xyz")
        d = r.json()
        self.assertEqual(d["total"], 0)

        # 3. 点击"新增用户"，填表单保存
        r = self.c.post("/api/users", data=json.dumps({
            "username": "journey_test",
            "real_name": "流程测试",
            "role_id": self.role.id,
            "dept": "测试部门",
            "phone": "13100000000",
            "email": "test@journey.com",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        new_id = r.json()["user"]["id"]

        # 4. 回到列表，搜刚建的用户 → 找到了
        r = self.c.get("/api/users?keyword=流程测试")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["users"][0]["real_name"], "流程测试")
        self.assertEqual(d["users"][0]["dept"], "测试部门")

        # 5. 点"编辑"，改姓名和部门
        r = self.c.patch(f"/api/users/{new_id}", data=json.dumps({
            "real_name": "流程测试改", "dept": "新部门",
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["real_name"], "流程测试改")

        # 6. 点"停用"
        r = self.c.patch(f"/api/users/{new_id}/status", data=json.dumps({
            "is_active": False,
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 按停用筛选，能找到它
        r = self.c.get(f"/api/users?status=inactive&keyword=流程")
        d = r.json()
        self.assertEqual(d["total"], 1)

        # 7. 点"删除"
        r = self.c.delete(f"/api/users/{new_id}")
        self.assertEqual(r.status_code, 200)
        # 列表里搜不到了
        r = self.c.get("/api/users?keyword=流程")
        d = r.json()
        self.assertEqual(d["total"], 0)


class RolesTest(TestCase):
    """角色管理：权限点列表 / 角色增删改查 / 成员"""

    @classmethod
    def setUpTestData(cls):
        cls.p1 = Permission.objects.create(name="用户管理", module="系统管理", code="user_manage", sort_order=1)
        cls.p2 = Permission.objects.create(name="角色管理", module="系统管理", code="role_manage", sort_order=2)
        cls.p3 = Permission.objects.create(name="个人中心", module="个人", code="profile", sort_order=3)
        cls.role = Role.objects.create(name="测试角色", description="测试用")
        u = User.objects.create_user(username="roletest", password="edu@123")
        UserProfile.objects.create(user=u, real_name="角色测试用户", role=cls.role)

    def setUp(self):
        self.c = Client()
        self.c.login(username="roletest", password="edu@123")

    def test_permission_list(self):
        r = self.c.get("/api/permissions")
        self.assertEqual(r.status_code, 200)
        modules = r.json()["modules"]
        self.assertGreaterEqual(len(modules), 2)

    def test_role_list(self):
        r = self.c.get("/api/roles")
        d = r.json()
        self.assertGreaterEqual(d["total"], 1)
        role = d["roles"][0]
        self.assertIn("member_count", role)
        self.assertIn("updated_at", role)

    def test_role_list_search(self):
        r = self.c.get("/api/roles?keyword=测试")
        d = r.json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["roles"][0]["name"], "测试角色")

    def test_role_create(self):
        r = self.c.post("/api/roles", data=json.dumps({
            "name": "新建角色", "description": "测试描述", "permission_ids": [self.p1.id, self.p2.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Role.objects.filter(name="新建角色").count(), 1)

    def test_role_create_duplicate(self):
        r = self.c.post("/api/roles", data=json.dumps({"name": "测试角色"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("已存在", r.json()["error"])

    def test_role_detail(self):
        r = self.c.get(f"/api/roles/{self.role.id}")
        d = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(d["role"]["name"], "测试角色")
        self.assertIn("permission_ids", d["role"])

    def test_role_update(self):
        r = self.c.patch(f"/api/roles/{self.role.id}", data=json.dumps({
            "name": "测试角色改", "description": "改过", "permission_ids": [self.p3.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.role.refresh_from_db()
        self.assertEqual(self.role.name, "测试角色改")
        self.assertEqual(list(self.role.permissions.values_list("id", flat=True)), [self.p3.id])

    def test_role_members(self):
        r = self.c.get(f"/api/roles/{self.role.id}/members")
        d = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(d["members"]), 1)
        self.assertEqual(d["members"][0]["username"], "roletest")
        self.assertEqual(d["members"][0]["dept"], "")

    def test_role_not_found(self):
        r = self.c.get("/api/roles/99999")
        self.assertEqual(r.status_code, 404)


class RolesJourneyTest(TestCase):
    """角色管理流程：管理员登录 → 看权限树 → 新建角色 → 编辑 → 看成员"""

    @classmethod
    def setUpTestData(cls):
        cls.p1 = Permission.objects.create(name="用户管理", module="系统管理", code="user_manage", sort_order=1)
        cls.p2 = Permission.objects.create(name="角色管理", module="系统管理", code="role_manage", sort_order=2)
        admin = User.objects.create_user(username="admin", password="admin123")
        admin.is_staff = True; admin.save()
        cls.role = Role.objects.create(name="管理员")
        UserProfile.objects.create(user=admin, real_name="管理员", role=cls.role)
        # 给角色分配一个人
        u = User.objects.create_user(username="member01", password="edu@123")
        UserProfile.objects.create(user=u, real_name="成员", role=cls.role)

    def setUp(self):
        self.c = Client()
        self.c.login(username="admin", password="admin123")

    def test_journey_role_crud(self):
        """管理员登录 → 打开权限树 → 新建角色勾权限 → 编辑改名 → 查看成员"""
        # 1. 取权限树（新增角色时要展示勾选面板）
        r = self.c.get("/api/permissions")
        modules = r.json()["modules"]
        self.assertGreaterEqual(len(modules), 1)

        # 2. 新建角色，勾两个权限
        r = self.c.post("/api/roles", data=json.dumps({
            "name": "流程角色", "description": "流程测试",
            "permission_ids": [self.p1.id, self.p2.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        new_id = r.json()["role"]["id"]

        # 3. 回到列表 → 搜得到
        r = self.c.get("/api/roles?keyword=流程")
        d = r.json()
        self.assertEqual(d["total"], 1)

        # 4. 点"编辑" → 取详情回填
        r = self.c.get(f"/api/roles/{new_id}")
        d = r.json()
        self.assertEqual(len(d["role"]["permission_ids"]), 2)

        # 5. 改角色名，换权限
        r = self.c.patch(f"/api/roles/{new_id}", data=json.dumps({
            "name": "流程角色改", "permission_ids": [self.p1.id],
        }), content_type="application/json")
        self.assertEqual(r.status_code, 200)

        # 6. 看成员弹窗
        r = self.c.get(f"/api/roles/{self.role.id}/members")
        d = r.json()
        self.assertEqual(len(d["members"]), 2)  # admin + member01


class ProfileTest(TestCase):
    """个人中心：资料读写 / 头像 / 改密码 / 换绑手机"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="profiletest", password="edu@123")
        role = Role.objects.create(name="测试角色")
        UserProfile.objects.create(user=cls.user, real_name="测试用户", phone="13800001111", dept="测试部", email="test@test.com", bio="个人说明", role=role)

    def setUp(self):
        self.c = Client()
        self.c.login(username="profiletest", password="edu@123")

    def test_get_profile(self):
        r = self.c.get("/api/profile")
        d = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(d["profile"]["real_name"], "测试用户")
        self.assertEqual(d["profile"]["phone"], "13800001111")

    def test_patch_profile(self):
        r = self.c.patch("/api/profile", data=json.dumps({"real_name": "改过", "dept": "新部门"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["real_name"], "改过")

    def test_avatar(self):
        r = self.c.patch("/api/profile/avatar", data=json.dumps({"avatar": "data:image/png;base64,xxx"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_password_wrong_old(self):
        r = self.c.post("/api/profile/password", data=json.dumps({"old_password": "wrong", "new_password": "x", "code": "123456"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("原密码", r.json()["error"])

    def test_password_ok(self):
        r = self.c.post("/api/profile/password", data=json.dumps({"old_password": "edu@123", "new_password": "newpass", "code": "123456"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # 新密码能登录
        ok = self.c.login(username="profiletest", password="newpass")
        self.assertTrue(ok)

    def test_phone_bad_format(self):
        r = self.c.post("/api/profile/phone", data=json.dumps({"code_old": "123456", "new_phone": "abc", "code_new": "123456"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_phone_ok(self):
        r = self.c.post("/api/profile/phone", data=json.dumps({"code_old": "123456", "new_phone": "13900009999", "code_new": "123456"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.phone, "13900009999")
