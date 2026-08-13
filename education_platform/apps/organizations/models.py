from django.conf import settings
from django.db import models


class College(models.Model):
    """岗位能力下发目标学院。capabilities 模块依赖，保留不动。"""
    name = models.CharField("学院名称", max_length=100, unique=True)
    org = models.ForeignKey(
        "Organization", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="linked_colleges", verbose_name="关联机构",
    )
    is_enabled = models.BooleanField("是否启用", default=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "organization_college"
        ordering = ["sort_order", "id"]
        verbose_name = "学院"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Organization(models.Model):
    """组织机构（树形，自引用）。"""
    name = models.CharField("机构名称", max_length=100)
    org_type = models.CharField("机构类型", max_length=50)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="children", verbose_name="上级机构",
    )
    leader = models.CharField("负责人", max_length=50, blank=True)
    description = models.TextField("机构说明", blank=True)
    sort_order = models.PositiveIntegerField("排序", default=0)
    is_enabled = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "organization_org"
        ordering = ["sort_order", "id"]
        verbose_name = "组织机构"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Class(models.Model):
    """班级。"""
    class Status(models.TextChoices):
        ACTIVE = "active", "启用"
        GRADUATED = "graduated", "毕业"

    name = models.CharField("班级名称", max_length=100)
    code = models.CharField("班级编号", max_length=50, unique=True)
    org = models.ForeignKey(
        Organization, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="classes", verbose_name="所属机构",
    )
    major = models.CharField("专业", max_length=100, blank=True)
    grade = models.CharField("年级", max_length=20, blank=True)
    teacher = models.CharField("班主任", max_length=50, blank=True)
    status = models.CharField(
        "状态", max_length=20, choices=Status.choices, default=Status.ACTIVE,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "organization_class"
        ordering = ["-created_at"]
        verbose_name = "班级"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name

    @property
    def student_count(self):
        return self.students.count()


class Student(models.Model):
    """学生。"""
    name = models.CharField("姓名", max_length=50)
    student_id = models.CharField("学号", max_length=20, unique=True)
    major = models.CharField("专业", max_length=100, blank=True)
    grade = models.CharField("年级", max_length=20, blank=True)
    class_group = models.ForeignKey(
        Class, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="students", verbose_name="所属班级",
    )
    phone = models.CharField("手机号", max_length=20, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="student_profile", verbose_name="关联账号",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "organization_student"
        ordering = ["-created_at"]
        verbose_name = "学生"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name}（{self.student_id}）"
