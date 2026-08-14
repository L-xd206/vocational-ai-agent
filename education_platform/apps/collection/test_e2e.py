"""岗位采集前后端浏览器端到端测试。

默认跳过，避免普通后端测试依赖浏览器。执行方式（PowerShell）：
    $env:RUN_COLLECTION_E2E='1'
    python manage.py test apps.collection.test_e2e -v 2

测试使用 Django 隔离数据库，不会修改本地业务数据，也不会发起真实招聘网站采集。
"""

import os
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from apps.capabilities.services import merge_official_tree
from apps.industry.models import Chain, Job

from .models import CrawlSource
from .services import create_analysis_batch


try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - 仅在未安装测试依赖时触发
    sync_playwright = None


CHROME_CANDIDATES = [
    Path(os.environ.get("COLLECTION_E2E_CHROME", "")),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
CHROME_PATH = next((path for path in CHROME_CANDIDATES if path.is_file()), None)
E2E_ENABLED = (
    os.environ.get("RUN_COLLECTION_E2E") == "1"
    and sync_playwright is not None
    and CHROME_PATH is not None
)


@skipUnless(E2E_ENABLED, "设置 RUN_COLLECTION_E2E=1 且安装 Playwright/Chrome 后运行")
class CollectionBrowserE2ETests(StaticLiveServerTestCase):
    """从页面点击到底层数据库的完整岗位采集交互回归测试。"""

    @classmethod
    def setUpClass(cls):
        # Playwright 同步接口内部维护事件循环；LiveServer测试仍通过同步ORM准备隔离数据。
        cls.previous_async_unsafe = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            headless=True,
            executable_path=str(CHROME_PATH),
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()
        if cls.previous_async_unsafe is None:
            os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
        else:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = cls.previous_async_unsafe

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="e2e-admin",
            password="e2e-password",
        )
        chain = Chain.objects.create(name="端到端测试产业链")
        self.job = Job.objects.create(
            chain=chain,
            name="端到端测试岗位",
            search_keywords=["端到端测试岗位"],
        )
        # TransactionTestCase 会在用例间 flush 数据，RunPython 种子不会自动重跑，
        # 因而每个浏览器用例显式准备自己的采集源夹具。
        self.source, _ = CrawlSource.objects.get_or_create(
            code="mohrss",
            defaults={
                "name": "中国公共招聘网",
                "base_url": "http://job.mohrss.gov.cn",
                "interval_minutes": 1440,
                "is_enabled": True,
                "config_json": {"pages": 3, "timeout": 20},
            },
        )
        merge_official_tree(self.job, [{
            "name": "正式岗位能力",
            "college": "未分配学院",
            "units": [{
                "name": "正式能力单元",
                "children": [{"name": "正式知识点"}],
            }],
        }])
        self.batch = create_analysis_batch(self.job, [{
            "name": "AI候选岗位能力",
            "college": "未分配学院",
            "units": [{
                "name": "AI候选能力单元",
                "children": [
                    {"name": "准备引用的知识点", "evidence": ["引用测试证据"]},
                    {"name": "准备拒纳的知识点", "evidence": ["拒纳测试证据"]},
                ],
            }],
        }])
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.page = self.context.new_page()
        self.page.goto(f"{self.live_server_url}/login.html")
        result = self.page.evaluate(
            """async ({username, password}) => {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                return {status: response.status, body: await response.json()};
            }""",
            {"username": "e2e-admin", "password": "e2e-password"},
        )
        self.assertEqual(result["status"], 200)

    def tearDown(self):
        self.context.close()

    def test_source_list_editor_and_original_graph(self):
        self.page.goto(f"{self.live_server_url}/岗位数据采集.html")
        self.page.locator(".job-tree").first.wait_for()

        self.page.locator("#configButton").click()
        source_row = self.page.locator(".source-row").filter(has_text="中国公共招聘网")
        source_row.wait_for()
        self.assertEqual(source_row.count(), 1)
        self.assertIn("已启用", source_row.inner_text())
        self.assertLessEqual(source_row.evaluate("element => element.getBoundingClientRect().height"), 64)

        source_row.locator("[data-edit-source]").click()
        address = self.page.locator('[data-field="base_url"]')
        self.assertTrue(address.is_editable() is False)
        self.assertEqual(address.input_value(), "http://job.mohrss.gov.cn")

        self.page.locator('[data-field="interval_minutes"]').fill("90")
        self.page.locator('[data-field="pages"]').fill("4")
        self.page.locator('[data-field="is_enabled"]').uncheck()
        self.page.locator("#saveConfigButton").click()
        self.page.locator(".source-row").wait_for()
        self.assertIn("已停用", self.page.locator(".source-row").inner_text())

        self.source.refresh_from_db()
        self.assertEqual(self.source.interval_minutes, 90)
        self.assertEqual(self.source.config_json["pages"], 4)
        self.assertFalse(self.source.is_enabled)
        self.assertEqual(self.source.base_url, "http://job.mohrss.gov.cn")

        self.page.locator('.modal-close[data-close="configModal"]').click()

        self.page.locator("#originalButton").click()
        self.page.wait_for_function(
            "document.querySelector('#originalButton').textContent === '显示AI分析图'"
        )
        self.assertIn("正式岗位能力", self.page.locator("#treeContent").inner_text())
        self.assertIn("当前显示正式能力图谱", self.page.locator("#statusText").inner_text())

    def test_adopt_and_reject_flow_across_both_pages(self):
        self.page.goto(f"{self.live_server_url}/岗位数据采集.html")
        self.page.locator(".job-tree").first.wait_for()

        adopt_card = self.page.locator(".node-card").filter(has_text="准备引用的知识点")
        adopt_card.locator('[data-action="adopt"]').click()
        self.page.get_by_text("引用成功，节点已更新到能力图谱").wait_for()
        self.assertEqual(adopt_card.locator('[data-action="adopt"]').count(), 0)

        reject_card = self.page.locator(".node-card").filter(has_text="准备拒纳的知识点")
        reject_card.locator('[data-action="reject"]').click()
        self.page.locator("#messageConfirm").click()
        self.page.get_by_text("已移入未采纳数据").wait_for()
        self.assertEqual(
            self.page.locator(".node-card").filter(has_text="准备拒纳的知识点").count(),
            0,
        )

        self.page.goto(f"{self.live_server_url}/未采纳数据.html")
        self.page.get_by_text("准备拒纳的知识点").wait_for()
        rejected_text = self.page.locator("#treeContent").inner_text()
        self.assertIn("准备拒纳的知识点", rejected_text)
        self.assertIn("AI候选岗位能力", rejected_text)
        self.assertIn("已拒纳", rejected_text)
        self.assertNotIn("已存在", rejected_text)

        restored_card = self.page.locator(".node-card").filter(has_text="准备拒纳的知识点")
        restored_card.locator('[data-action="restore"]').click()
        self.page.get_by_text("节点已返回岗位数据采集，尚未写入正式能力图谱").wait_for()
        self.assertEqual(
            self.page.locator(".node-card").filter(has_text="准备拒纳的知识点").count(),
            0,
        )

        self.page.goto(f"{self.live_server_url}/岗位数据采集.html")
        restored_candidate = self.page.locator(".node-card").filter(
            has_text="准备拒纳的知识点"
        )
        restored_candidate.wait_for()
        self.assertIn("AI新增", restored_candidate.inner_text())
        self.assertEqual(restored_candidate.locator('[data-action="adopt"]').count(), 1)
