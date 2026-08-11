from django.test import TestCase

from apps.industry.models import Chain, Job
from apps.organizations.models import College

from .models import CapabilityNode
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
