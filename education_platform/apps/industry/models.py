from django.db import models

class Chain(models.Model):
    name = models.CharField("产业链名称", max_length=100, unique=True)
    description = models.CharField("描述", max_length=500, blank=True)
    is_enabled = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "chain"
        verbose_name = "产业链"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class Job(models.Model):
    chain = models.ForeignKey(Chain, on_delete=models.CASCADE, related_name="jobs", verbose_name="所属产业链")
    name = models.CharField("标准岗位名", max_length=100)
    aliases = models.JSONField("别名列表", default=list)
    search_keywords = models.JSONField("搜索关键词", default=list)
    is_confirmed = models.BooleanField("已确认", default=False)
    is_enabled = models.BooleanField("是否启用", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "job"
        verbose_name = "岗位"
        verbose_name_plural = verbose_name
        unique_together = [("chain", "name")]

    def __str__(self):
        return f"{self.chain.name} / {self.name}"
