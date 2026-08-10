from django.test import TestCase

from apps.industry.models import Chain, Job
from apps.organizations.models import College

from .models import AnalysisNode, CapabilityNode
from .services import (
    adopt_analysis_node,
    create_analysis_batch,
    merge_official_tree,
    reject_analysis_node,
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
        self.college = College.objects.create(name="测试智能制造学院")

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
