from django.conf import settings
from django.db import models


class Notification(models.Model):
    """通知。管理员手发走 草稿→发布 流程；系统事件直接 status=published 写入。"""

    class Type(models.TextChoices):
        SYSTEM = "system", "系统公告"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        OFFLINE = "offline", "已下架"

    title = models.CharField("通知标题", max_length=100)
    content = models.TextField("通知内容")
    type = models.CharField(
        "类型", max_length=20, choices=Type.choices, default=Type.SYSTEM,
    )
    status = models.CharField(
        "状态", max_length=20, choices=Status.choices, default=Status.DRAFT,
    )
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="published_notifications", verbose_name="发布人",
    )
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    audience = models.ForeignKey(
        "accounts.Role", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="notifications", verbose_name="受众角色",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        db_table = "notification_notice"
        ordering = ["-created_at"]
        verbose_name = "通知"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.title


class NotificationRead(models.Model):
    """某用户对某通知的已读记录。有记录=已读。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notification_reads", verbose_name="用户",
    )
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE,
        related_name="reads", verbose_name="通知",
    )
    read_at = models.DateTimeField("已读时间", auto_now_add=True)

    class Meta:
        db_table = "notification_notice_read"
        unique_together = [("user", "notification")]
        verbose_name = "通知已读记录"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user} 已读 {self.notification}"


class SystemLog(models.Model):
    """系统日志。操作人冗余存 id+名称，扩展信息存 detail JSON。"""

    class LogType(models.TextChoices):
        LOGIN = "login", "登录日志"
        OPERATION = "operation", "操作日志"

    log_type = models.CharField("日志类型", max_length=20, choices=LogType.choices)
    content = models.TextField("日志内容")
    user_id = models.IntegerField("操作人ID", null=True, blank=True)
    username = models.CharField("操作人名称", max_length=50, blank=True)
    ip = models.CharField("IP", max_length=50, blank=True)
    duration_ms = models.IntegerField("耗时(毫秒)", null=True, blank=True)
    detail = models.JSONField("详情", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "notification_system_log"
        ordering = ["-created_at"]
        verbose_name = "系统日志"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"[{self.get_log_type_display()}] {self.content[:50]}"
