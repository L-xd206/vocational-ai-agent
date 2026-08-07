from django.db import models


class College(models.Model):
    """岗位能力下发目标学院。"""
    name = models.CharField("学院名称", max_length=100, unique=True)
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
