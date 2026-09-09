import json
from unittest.mock import patch

from django.test import TestCase

from ai.capability_generation import build_prompt

from apps.industry.models import Chain, Job
from apps.collection.models import CrawlSource, CrawlTask
from apps.collection.services import save_crawl_result, valid_job_requirements
from apps.organizations.models import Organization

from .models import CapabilityNode, parse_abilities_to_tree
from .services import (
    merge_official_tree,
    serialize_official_tree,
)


class CapabilityNodeServicesTests(TestCase):
    def setUp(self):
        self.chain = Chain.objects.create(name="测试产业链")
        self.job = Job.objects.create(
            chain=self.chain,
            name="工业机器人操作员",
            search_keywords=["工业机器人操作员", "机器人调试", "机器人运维"],
        )
        self.college = Organization.objects.create(
            name="测试智能制造学院",
            org_type="学院",
        )

    def test_legacy_tree_is_migrated_to_three_node_levels(self):
        merge_official_tree(self.job, [{
            "name": "机器人系统调试",
            "college": self.college.name,
            "children": [
                {"name": "零点校准", "enabled": True},
                {"name": "通信测试", "enabled": True},
            ],
        }], origin="legacy")

        self.assertEqual(CapabilityNode.objects.filter(job=self.job, node_type="ability").count(), 1)
        self.assertGreaterEqual(CapabilityNode.objects.filter(job=self.job, node_type="unit").count(), 1)
        self.assertEqual(CapabilityNode.objects.filter(job=self.job, node_type="point").count(), 2)
        tree = serialize_official_tree(self.job)
        self.assertEqual(tree[0]["name"], "机器人系统调试")
        self.assertEqual(tree[0]["college"], self.college.name)
        self.assertEqual(tree[0]["organization_id"], self.college.id)
        self.assertEqual(tree[0]["course_matches"], [])

    def test_serialized_tree_includes_course_matches(self):
        ability = CapabilityNode.objects.create(
            job=self.job,
            node_type="ability",
            name="加工准备与工程识图",
            course_matches=[{
                "course_name": "数控加工工艺与编程",
                "matched_content": "工艺规程与夹具选择",
            }],
        )

        tree = serialize_official_tree(self.job)

        self.assertEqual(tree[0]["id"], ability.id)
        self.assertEqual(tree[0]["course_matches"][0]["course_name"], "数控加工工艺与编程")

    def test_ai_prompt_contains_official_tree_json(self):
        official_tree = [{
            "name": "机器人维护",
            "college": self.college.name,
            "units": [{
                "name": "机器人本体维护",
                "children": [{"name": "关节润滑"}],
            }],
        }]

        prompt = build_prompt(
            self.job.name,
            "负责工业机器人维修与关节润滑",
            official_tree,
        )

        official_json = json.dumps(
            official_tree,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertIn(official_json, prompt)
        self.assertIn("语义相同或高度相近", prompt)
        self.assertIn("复用正式节点的原名称", prompt)
        self.assertIn("负责工业机器人维修与关节润滑", prompt)

    def test_structured_ai_tree_keeps_units_and_points(self):
        raw_text = json.dumps({
            "job_name": self.job.name,
            "abilities": [{
                "name": "机器人维护",
                "college": self.college.name,
                "units": [{
                    "name": "机器人本体维护",
                    "evidence": "机器人维修",
                    "children": [{
                        "name": "关节润滑",
                        "evidence": "关节保养",
                        "assessment": "润滑结果符合规范",
                    }],
                }],
            }],
        }, ensure_ascii=False)

        tree = parse_abilities_to_tree(raw_text)

        self.assertEqual(tree[0]["name"], "机器人维护")
        self.assertEqual(tree[0]["units"][0]["name"], "机器人本体维护")
        point = tree[0]["units"][0]["children"][0]
        self.assertEqual(point["name"], "关节润滑")
        self.assertEqual(point["assessment"], "润滑结果符合规范")

    def test_ability_organization_can_be_updated(self):
        ability = CapabilityNode.objects.create(
            job=self.job,
            node_type="ability",
            name="机器人现场操作",
        )
        response = self.client.post(
            "/api/ability/node/organization",
            data=json.dumps({"node_id": ability.id, "organization_id": self.college.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        ability.refresh_from_db()
        self.assertEqual(ability.organization, self.college)
        self.assertEqual(response.json()["college"], self.college.name)

    def test_formal_tree_uses_accumulated_data_when_latest_crawl_has_no_new_items(self):
        source = CrawlSource.objects.create(
            name="累计数据测试来源",
            code="accumulated_test",
            base_url="https://example.com",
        )
        first_task = CrawlTask.objects.create(
            job=self.job,
            source=source,
            status="completed",
        )
        for index in range(10):
            save_crawl_result(first_task, {
                "title": self.job.name,
                "company": f"测试企业{index}",
                "requirements": f"负责工业机器人第{index}类设备的安装调试、运行检查与维护保养工作。",
                "source_url": f"https://example.com/jobs/{index}",
            })
        CrawlTask.objects.create(
            job=self.job,
            source=source,
            status="completed",
            total_results=10,
            new_results=0,
        )

        self.assertEqual(len(valid_job_requirements(self.job)), 10)

        tree_response = self.client.get(f"/api/ability/{self.job.id}/tree")
        self.assertEqual(tree_response.status_code, 200)
        self.assertEqual(tree_response.json()["data_count"], 10)
        self.assertEqual(tree_response.json()["data_status"], "ready")

        with patch("apps.capabilities.views.threading.Thread") as thread_class:
            generate_response = self.client.post(
                "/api/ability/generate",
                data=json.dumps({"job_id": self.job.id}),
                content_type="application/json",
            )
        self.assertEqual(generate_response.status_code, 200)
        self.assertEqual(generate_response.json()["status"], "processing")
        thread_class.return_value.start.assert_called_once_with()
