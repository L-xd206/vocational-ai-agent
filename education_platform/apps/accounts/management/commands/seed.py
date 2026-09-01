"""一键灌入所有模块的种子数据（幂等，可重复执行）

用法：python manage.py seed
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "一键灌入全部模块种子数据（幂等）"

    def handle(self, *args, **options):
        self.stdout.write("=== 开始灌入种子数据 ===\n")

        self.stdout.write("[organizations]")
        call_command("seed_organizations")

        self.stdout.write("\n[accounts]")
        call_command("seed_accounts")

        self.stdout.write("\n[notifications]")
        call_command("seed_notifications")

        self.stdout.write("\n[teaching]")
        call_command("seed_teaching")

        self.stdout.write("\n[learning]")
        call_command("seed_learning")

        self.stdout.write(self.style.SUCCESS("\n=== 全部 seed 完成 ==="))
