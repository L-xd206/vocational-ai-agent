from django.db import models

class CrawlTask(models.Model):
    """爬取任务"""
    job = models.ForeignKey("chain.Job", on_delete=models.CASCADE, related_name="crawl_tasks", verbose_name="岗位")
    status = models.CharField(max_length=20, default="pending", choices=[
        ("pending", "待执行"), ("running", "执行中"), ("completed", "已完成"), ("failed", "失败")
    ])
    total_keywords = models.IntegerField(default=0)
    total_results = models.IntegerField(default=0)
    results_json = models.JSONField("原始结果", default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crawl_task"
        verbose_name = "爬取任务"

    def __str__(self):
        return f"Task #{self.id} - {self.job.name}"


class JobListing(models.Model):
    """单条招聘信息"""
    task = models.ForeignKey(CrawlTask, on_delete=models.CASCADE, related_name="listings", verbose_name="所属任务")
    title = models.CharField("岗位名称", max_length=200)
    company = models.CharField("公司", max_length=200)
    city = models.CharField("城市", max_length=100, blank=True)
    salary = models.CharField("薪资", max_length=100, blank=True)
    education = models.CharField("学历", max_length=50, blank=True)
    requirements = models.TextField("任职要求", blank=True)
    headcount = models.CharField("招聘人数", max_length=20, blank=True)
    post_date = models.CharField("发布日期", max_length=50, blank=True)
    source = models.CharField("来源", max_length=100, blank=True)

    class Meta:
        db_table = "job_listing"
        verbose_name = "招聘信息"
