from datetime import timedelta
import time

from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from apps.collection.models import CrawlSource
from apps.collection.services import create_crawl_task
from apps.collection.tasks import execute_crawl_task
from apps.industry.models import Job


class Command(BaseCommand):
    help = "执行所有已到期采集来源下的启用岗位"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="作为常驻调度进程持续检查到期任务",
        )
        parser.add_argument(
            "--poll-seconds",
            type=int,
            default=60,
            help="常驻模式的检查间隔秒数，默认60秒",
        )

    def handle(self, *args, **options):
        poll_seconds = max(5, options["poll_seconds"])
        if not options["loop"]:
            self.run_once()
            return

        self.stdout.write(
            self.style.SUCCESS(f"岗位采集调度器已启动，每 {poll_seconds} 秒检查一次")
        )
        try:
            while True:
                self.run_once()
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("岗位采集调度器已停止"))

    def run_once(self):
        now = timezone.now()
        source_ids = list(
            CrawlSource.objects.filter(is_enabled=True)
            .filter(models.Q(next_run_at__isnull=True) | models.Q(next_run_at__lte=now))
            .values_list("id", flat=True)
        )
        if not source_ids:
            self.stdout.write("当前没有已到期的采集来源")
            return

        jobs = list(
            Job.objects.filter(is_enabled=True, chain__is_enabled=True)
            .select_related("chain")
            .order_by("id")
        )

        for source_id in source_ids:
            with transaction.atomic():
                source = CrawlSource.objects.select_for_update().get(id=source_id)
                if not source.is_enabled:
                    continue
                if source.next_run_at and source.next_run_at > now:
                    continue
                source.last_run_at = now
                source.next_run_at = now + timedelta(minutes=source.interval_minutes)
                source.save(update_fields=["last_run_at", "next_run_at"])

            self.stdout.write(f"开始执行采集来源：{source.name}")
            for job in jobs:
                task, created = create_crawl_task(
                    job=job,
                    source=source,
                    trigger_type="scheduled",
                )
                if not created:
                    self.stdout.write(f"[跳过] {job.name}：已有任务正在执行")
                    continue
                execute_crawl_task(task.id, auto_analyze=True)
                task.refresh_from_db()
                if task.status == "failed":
                    self.stderr.write(f"[失败] {source.name} / {job.name}：{task.error_message}")
                else:
                    self.stdout.write(
                        f"[完成] {source.name} / {job.name}："
                        f"采集{task.total_results}条，新增{task.new_results}条"
                    )

