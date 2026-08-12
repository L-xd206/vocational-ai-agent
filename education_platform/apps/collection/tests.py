import json
from unittest.mock import patch

from django.test import TestCase

from apps.capabilities.services import merge_official_tree
from apps.industry.models import Chain, Job
from apps.organizations.models import College

from .models import AnalysisBatch, AnalysisNode, CrawlSource, CrawlTask, JobListing
from .services import (
    adopt_analysis_node,
    create_analysis_batch,
    reject_analysis_node,
    save_crawl_result,
)


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
        first_task = CrawlTask.objects.create(job=job, source=source)
        second_task = CrawlTask.objects.create(job=job, source=source)
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
