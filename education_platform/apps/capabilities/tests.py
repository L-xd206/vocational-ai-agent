import json

from django.test import TestCase

from ai.capability_generation import build_prompt

from apps.industry.models import Chain, Job
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
