from django.db import models
from django.conf import settings

class Permission(models.Model):
      """权限点 = 一个可访问的页面"""
      name = models.CharField("页面名", max_length=100, unique=True)
      module = models.CharField("所属模块", max_length=50)
      code = models.CharField("权限码", max_length=50, unique=True)
      url = models.CharField("页面路径", max_length=200, blank=True)
      sort_order = models.PositiveIntegerField("排序", default=0)

      class Meta:
          db_table = "account_permission"
          verbose_name = "权限点"
          verbose_name_plural = verbose_name

      def __str__(self):
          return f"[{self.module}] {self.name}"

class Role(models.Model):
    """角色表"""
    name = models.CharField("角色名称", max_length=50, unique=True)
    description = models.CharField("角色说明", max_length=200, blank=True)
    is_builtin = models.BooleanField("内置角色", default=False)
    is_enabled = models.BooleanField("是否启用", default=True)
    permissions = models.ManyToManyField(
        Permission,
        related_name="roles",
        blank=True,
        verbose_name="可访问页面",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "account_role"
        verbose_name = "角色"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name

    @property
    def permission_codes(self):
        """该角色挂的权限码列表（权限校验用）"""
        return list(self.permissions.values_list("code", flat=True))

class UserProfile(models.Model):
    """用户资料，OneToOne 关联 Django 内置 User"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="账号",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name="角色",
    )
    real_name = models.CharField("姓名", max_length=50, blank=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profiles",
        verbose_name="所属组织",
    )
    phone = models.CharField("手机号", max_length=20, blank=True)
    email = models.CharField("邮箱", max_length=100, blank=True)
    bio = models.TextField("个人说明", blank=True)
    avatar = models.CharField("头像", max_length=500, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "account_profile"
        verbose_name = "用户资料"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.real_name or self.user.username
    
    
