"""预置通知测试数据（幂等，可重复执行）

用法：python manage.py seed_notifications
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.api import get_enabled_roles
from apps.notifications.models import Notification

User = get_user_model()


class Command(BaseCommand):
    help = "预置通知测试数据（幂等）"

    def handle(self, *args, **options):
        self.seed_notifications()
        self.stdout.write(self.style.SUCCESS(
            f"seed_notifications 完成：{Notification.objects.count()} 通知"
        ))

    def seed_notifications(self):
        admin = User.objects.filter(username="admin").first()
        teacher_role = get_enabled_roles().filter(name="教师").first()
        now = timezone.now()

        # 已发布通知（所有人可见）
        published = [
            ("本周平台维护通知", "本周六 02:00-04:00 进行系统维护，期间部分功能可能短暂不可用。"),
            ("实训安全须知", "进入实训室须穿戴劳保用品，严禁擅自操作急停旁路。"),
            ("暑期实训开放安排", "本学期暑期开放实训室预约已启动，请提前在系统内完成预约。"),
        ]
        for title, content in published:
            n, created = Notification.objects.get_or_create(
                title=title,
                defaults={"content": content, "status": "published", "publisher": admin, "published_at": now},
            )
            self.stdout.write(f"{'已创建' if created else '已存在'}：{n.title}")

        # 定向「教师」角色的通知
        n, created = Notification.objects.get_or_create(
            title="课程内容已调整",
            defaults={
                "content": "《工业机器人操作与编程》第 3 章知识点已更新，请及时同步学习进度。",
                "status": "published", "publisher": None, "audience": teacher_role, "published_at": now,
            },
        )
        self.stdout.write(f"{'已创建' if created else '已存在'}：{n.title}（定向教师）")

        # 草稿通知
        n, created = Notification.objects.get_or_create(
            title="新学期开课提醒草稿",
            defaults={"content": "请各位教师于开课前完成教学安排与课程资源检查。", "status": "draft", "publisher": admin},
        )
        self.stdout.write(f"{'已创建' if created else '已存在'}：{n.title}（草稿）")
