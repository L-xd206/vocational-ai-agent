import json
from unittest.mock import patch

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.capabilities.services import merge_official_tree
from apps.industry.models import Chain, Job
from apps.organizations.models import College

from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask, JobListing
from .services import (
    adopt_analysis_node,
    create_crawl_source,
    create_analysis_batch,
    create_crawl_task,
    reject_analysis_node,
    save_crawl_result,
    serialize_rejected_tree,
)
from .tasks import execute_crawl_task, start_analysis_for_task


class ListingDeduplicationTests(TestCase):
    def test_same_listing_is_updated_instead_of_duplicated(self):
        chain = Chain.objects.create(name="采集测试产业链")
        job = Job.objects.create(
            chain=chain,
            name="采集测试岗位",
            search_keywords=["采集测试岗位", "测试操作", "测试维护"],
        )
        source = CrawlSource.objects.create(
            name="测试招聘来源",
            code="test_source",
            base_url="https://example.com",
        )
        first_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        second_task = CrawlTask.objects.create(job=job, source=source, status="completed")
        item = {
            "title": "采集测试岗位",
            "company": "测试公司",
            "city": "杭州",
            "requirements": "负责测试设备操作、调试与维护工作。",
            "source_url": "https://example.com/jobs/1",
        }

        _, first_created = save_crawl_result(first_task, item)
        listing, second_created = save_crawl_result(second_task, item)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(JobListing.objects.count(), 1)
        self.assertEqual(listing.task_id, second_task.id)


class CrawlSourceAndTaskTests(TestCase):
    def setUp(self):
        self.chain = Chain.objects.create(name="任务测试产业链")
        self.job = Job.objects.create(
            chain=self.chain,
            name="任务测试岗位",
            search_keywords=["任务测试岗位"],
        )
        self.source = CrawlSource.objects.get(code="mohrss")

    def test_unregistered_source_code_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "尚未实现对应采集器"):
            create_crawl_source({
                "name": "尚未实现的网站",
                "code": "not_implemented",
                "base_url": "https://example.com",
                "interval_minutes": 1440,
                "pages": 3,
            })

    def test_same_job_and_source_reuses_active_task(self):
        first, first_created = create_crawl_task(
            job=self.job, source=self.source, trigger_type="manual"
        )
        second, second_created = create_crawl_task(
            job=self.job, source=self.source, trigger_type="scheduled"
        )
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.id, second.id)

    @patch("apps.collection.tasks.start_analysis_for_task")
    @patch("apps.collection.crawlers.registry.get_crawler")
    def test_new_results_trigger_analysis(self, crawler_getter, analysis_mock):
        crawler_getter.return_value.crawl.return_value = [{
            "title": "任务测试岗位",
            "company": "测试公司",
            "requirements": "负责测试设备的运行、维护和故障处理工作。",
            "source_url": "https://example.com/job/1",
        }]
        task, _ = create_crawl_task(
            job=self.job, source=self.source, trigger_type="manual"
        )
        execute_crawl_task(task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.new_results, 1)
        analysis_mock.assert_called_once_with(task.id)

    def test_insufficient_data_creates_skipped_analysis(self):
        task = CrawlTask.objects.create(
            job=self.job,
            source=self.source,
            status="completed",
        )
        batch = start_analysis_for_task(task.id)
        self.assertEqual(batch.status, "skipped")
        self.assertIn("暂不生成能力图谱", batch.error_message)

    @patch("apps.collection.management.commands.run_due_crawls.execute_crawl_task")
    def test_due_command_schedules_only_enabled_jobs(self, execute_mock):
        Job.objects.create(
            chain=self.chain,
            name="已禁用岗位",
            search_keywords=["已禁用岗位"],
            is_enabled=False,
        )
        self.source.is_enabled = True
        self.source.next_run_at = timezone.now()
        self.source.save(update_fields=["is_enabled", "next_run_at"])

        call_command("run_due_crawls")

        tasks = CrawlTask.objects.filter(trigger_type="scheduled")
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().job_id, self.job.id)
        execute_mock.assert_called_once()

    def test_latest_trees_returns_enabled_jobs_and_latest_batch(self):
        user = get_user_model().objects.create_user(username="collection-reader")
        self.client.force_login(user)
        older = AnalysisBatch.objects.create(job=self.job, status="failed")
        latest = AnalysisBatch.objects.create(job=self.job, status="completed")
        AnalysisNode.objects.create(
            batch=latest,
            node_type="ability",
            name="最新岗位能力",
            normalized_name="最新岗位能力",
        )

        response = self.client.get("/api/collection/analysis/latest-trees")

        self.assertEqual(response.status_code, 200)
        item = next(
            row for row in response.json()["results"]
            if row["job"]["id"] == self.job.id
        )
        self.assertEqual(item["batch"]["id"], latest.id)
        self.assertNotEqual(item["batch"]["id"], older.id)
        self.assertEqual(item["tree"][0]["name"], "最新岗位能力")


class CandidateAnalysisServicesTests(TestCase):
    def setUp(self):
        chain = Chain.objects.create(name="候选分析测试产业链")
        self.job = Job.objects.create(
            chain=chain,
            name="工业机器人操作员",
            search_keywords=["工业机器人操作员", "机器人调试", "机器人运维"],
        )
        self.college = College.objects.create(name="候选分析测试学院")

    def test_candidate_match_and_adopt(self):
        merge_official_tree(self.job, [{
            "name": "机器人系统调试",
            "college": self.college.name,
            "units": [{"name": "本体调试", "children": []}],
        }])
        batch = create_analysis_batch(self.job, [{
            "name": "机器人系统调试",
            "college": self.college.name,
            "units": [{
                "name": "本体调试",
                "children": [{"name": "关节零点校准"}],
            }],
        }])

        ability = batch.nodes.get(node_type="ability")
        unit = batch.nodes.get(node_type="unit")
        point = batch.nodes.get(node_type="point")
        self.assertIsNotNone(ability.matched_node_id)
        self.assertIsNotNone(unit.matched_node_id)
        self.assertIsNone(point.matched_node_id)

        official = adopt_analysis_node(point)
        point.refresh_from_db()
        self.assertEqual(point.decision_status, "adopted")
        self.assertEqual(point.matched_node_id, official.id)
        self.assertEqual(official.node_type, "point")

    def test_reject_cascades_to_virtual_children(self):
        batch = create_analysis_batch(self.job, [{
            "name": "全新岗位能力",
            "college": self.college.name,
            "units": [{
                "name": "全新能力单元",
                "children": [{"name": "全新知识点"}],
            }],
        }])
        root = batch.nodes.get(node_type="ability")
        reject_analysis_node(root)
        self.assertFalse(
            AnalysisNode.objects.filter(batch=batch).exclude(decision_status="rejected").exists()
        )

    def test_rejected_leaf_keeps_ancestor_context(self):
        batch = create_analysis_batch(self.job, [{
            "name": "候选岗位能力",
            "college": self.college.name,
            "units": [{
                "name": "候选能力单元",
                "children": [{"name": "被拒纳知识点"}],
            }],
        }])
        point = batch.nodes.get(node_type="point")
        reject_analysis_node(point)

        tree = serialize_rejected_tree(batch)
        self.assertEqual(tree[0]["name"], "候选岗位能力")
        self.assertTrue(tree[0]["context_only"])
        self.assertEqual(tree[0]["children"][0]["name"], "候选能力单元")
        leaf = tree[0]["children"][0]["children"][0]
        self.assertEqual(leaf["name"], "被拒纳知识点")
        self.assertFalse(leaf["context_only"])

    @patch("ai.services.generate_capability_map")
    def test_candidate_analysis_sends_official_tree_to_ai(self, generate_mock):
        merge_official_tree(self.job, [{
            "name": "机器人维护",
            "college": self.college.name,
            "units": [{
                "name": "机器人本体维护",
                "children": [{"name": "关节润滑"}],
            }],
        }])
        source = CrawlSource.objects.create(
            name="候选分析测试来源",
            code="candidate_analysis_source",
            base_url="https://example.com",
        )
        task = CrawlTask.objects.create(job=self.job, source=source, status="completed")
        for index in range(10):
            JobListing.objects.create(
                task=task,
                job=self.job,
                crawl_source=source,
                fingerprint=f"fingerprint-{index}",
                title=self.job.name,
                requirements=f"第{index + 1}条工业机器人维修与关节润滑岗位要求",
            )
        batch = AnalysisBatch.objects.create(job=self.job, crawl_task=task, status="processing")
        generate_mock.return_value = {
            "abilities_text": json.dumps({
                "abilities": [{
                    "name": "机器人维护",
                    "college": self.college.name,
                    "units": [{
                        "name": "机器人本体维护",
                        "children": [{"name": "关节润滑"}],
                    }],
                }],
            }, ensure_ascii=False),
        }

        from .views import _run_candidate_analysis
        _run_candidate_analysis(batch.id)

        _, requirements = generate_mock.call_args.args
        official_tree = generate_mock.call_args.kwargs["official_tree"]
        self.assertEqual(len(requirements), 10)
        self.assertEqual(official_tree[0]["name"], "机器人维护")
        self.assertEqual(official_tree[0]["units"][0]["name"], "机器人本体维护")
        batch.refresh_from_db()
        self.assertEqual(batch.status, "completed")
