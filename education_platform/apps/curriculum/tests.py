import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.capabilities.models import CapabilityNode
from apps.industry.models import Chain, Job
from apps.organizations.models import Organization
from apps.resources.models import Textbook, TextbookNode

from .models import CourseTree, CourseTreeNode


User = get_user_model()


class CourseTreeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="智能制造学院", org_type="学院")
        cls.owner = User.objects.create_user(username="course_owner", password="edu@123")
        UserProfile.objects.create(user=cls.owner, organization=cls.organization)
        cls.textbook = Textbook.objects.create(
            organization=cls.organization,
            name="工业机器人技术基础",
        )
        cls.chapter = TextbookNode.objects.create(
            textbook=cls.textbook,
            node_type="chapter",
            name="机器人运动学",
        )
        cls.knowledge = TextbookNode.objects.create(
            textbook=cls.textbook,
            parent=cls.chapter,
            node_type="knowledge",
            name="坐标系变换",
        )
        chain = Chain.objects.create(name="智能制造产业链")
        job = Job.objects.create(chain=chain, name="工业机器人系统运维员")
        cls.ability = CapabilityNode.objects.create(
            job=job,
            node_type="ability",
            name="工业机器人技术基础",
            organization=cls.organization,
        )
        cls.unit = CapabilityNode.objects.create(
            job=job,
            parent=cls.ability,
            node_type="unit",
            name="机器人运动学与动力学",
        )
        cls.point = CapabilityNode.objects.create(
            job=job,
            parent=cls.unit,
            node_type="point",
            name="坐标系变换",
        )
        cls.tree = CourseTree.objects.create(
            organization=cls.organization,
            textbook=cls.textbook,
            name="工业机器人技术基础",
            source_ability=cls.ability,
            owner=cls.owner,
            source_snapshot={"name": cls.ability.name},
        )

    def test_course_tree_accepts_same_organization_owner_and_textbook(self):
        self.tree.full_clean()

    def test_course_tree_has_only_chapter_and_knowledge_levels(self):
        chapter = CourseTreeNode(
            tree=self.tree,
            node_type="chapter",
            name="机器人运动学",
            source_node=self.unit,
            textbook_node=self.chapter,
        )
        chapter.full_clean()
        chapter.save()
        knowledge = CourseTreeNode(
            tree=self.tree,
            parent=chapter,
            node_type="knowledge",
            name="坐标系变换",
            source_node=self.point,
            textbook_node=self.knowledge,
        )
        knowledge.full_clean()

    def test_knowledge_node_requires_chapter_parent(self):
        node = CourseTreeNode(
            tree=self.tree,
            node_type="knowledge",
            name="无父级知识点",
            source_node=self.point,
            textbook_node=self.knowledge,
        )
        with self.assertRaises(ValidationError):
            node.full_clean()

    def test_owner_must_belong_to_tree_organization(self):
        other_org = Organization.objects.create(name="信息工程学院", org_type="学院")
        other_owner = User.objects.create_user(username="other_owner", password="edu@123")
        UserProfile.objects.create(user=other_owner, organization=other_org)
        self.tree.owner = other_owner
        with self.assertRaises(ValidationError):
            self.tree.full_clean()

    def test_dispatch_creates_pending_course_tree_with_snapshot(self):
        self.tree.delete()
        self.client.login(username="course_owner", password="edu@123")
        response = self.client.post(
            "/api/curriculum/dispatch",
            data=json.dumps({
                "job_id": self.ability.job_id,
                "ability_ids": [self.ability.id],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created_count"], 1)
        dispatched = CourseTree.objects.get(
            organization=self.organization,
            source_ability=self.ability,
        )
        self.assertIsNone(dispatched.textbook)
        self.assertEqual(dispatched.source_snapshot["units"][0]["id"], self.unit.id)
        self.assertEqual(
            dispatched.source_snapshot["units"][0]["children"][0]["id"],
            self.point.id,
        )

    def test_duplicate_dispatch_is_skipped(self):
        self.tree.delete()
        self.client.login(username="course_owner", password="edu@123")
        payload = json.dumps({
            "job_id": self.ability.job_id,
            "ability_ids": [self.ability.id],
        })
        first = self.client.post("/api/curriculum/dispatch", data=payload, content_type="application/json")
        second = self.client.post("/api/curriculum/dispatch", data=payload, content_type="application/json")
        self.assertEqual(first.json()["created_count"], 1)
        self.assertEqual(second.json()["created_count"], 0)
        self.assertEqual(second.json()["skipped_count"], 1)

    def test_unassigned_ability_cannot_be_dispatched(self):
        self.ability.organization = None
        self.ability.save(update_fields=["organization", "updated_at"])
        self.client.login(username="course_owner", password="edu@123")
        response = self.client.post(
            "/api/curriculum/dispatch",
            data=json.dumps({
                "job_id": self.ability.job_id,
                "ability_ids": [self.ability.id],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("未分配学院", response.json()["error"])
