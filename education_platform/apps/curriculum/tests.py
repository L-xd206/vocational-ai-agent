import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import Permission, Role, UserProfile
from apps.capabilities.models import CapabilityNode
from apps.industry.models import Chain, Job
from apps.organizations.models import Organization
from apps.resources.models import Textbook, TextbookNode
from apps.teaching.models import CourseQuestion

from .models import CourseTree, CourseTreeNode
from .services import TeacherWorkProtectedError, save_ai_course_tree


User = get_user_model()


class CourseTreeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="智能制造学院", org_type="学院")
        cls.course_role = Role.objects.create(name="课程负责人")
        cls.manager_role = Role.objects.create(name="学院负责人")
        cls.owner = User.objects.create_user(username="course_owner", password="edu@123")
        UserProfile.objects.create(user=cls.owner, organization=cls.organization, role=cls.course_role)
        cls.manager = User.objects.create_user(username="college_manager", password="edu@123")
        UserProfile.objects.create(user=cls.manager, organization=cls.organization, role=cls.manager_role)
        cls.dispatch_permission = Permission.objects.create(
            module="能力图谱", name="岗位能力下发", code="capability_dispatch"
        )
        cls.dispatch_role = Role.objects.create(name="能力图谱负责人")
        cls.dispatch_role.permissions.add(cls.dispatch_permission)
        cls.dispatcher = User.objects.create_user(username="capability_manager", password="edu@123")
        UserProfile.objects.create(user=cls.dispatcher, role=cls.dispatch_role)
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
            total_hours=48,
            credits=3,
            ai_generation_status="ready",
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

    @patch("apps.curriculum.views.threading.Thread")
    def test_dispatch_creates_pending_course_tree_with_snapshot(self, thread):
        self.tree.delete()
        self.client.login(username="capability_manager", password="edu@123")
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
        dispatched.refresh_from_db()
        self.assertEqual(dispatched.ai_generation_status, "processing")
        thread.assert_called_once()

    @patch("apps.curriculum.views.threading.Thread")
    def test_duplicate_dispatch_is_skipped(self, thread):
        self.tree.delete()
        self.client.login(username="capability_manager", password="edu@123")
        payload = json.dumps({
            "job_id": self.ability.job_id,
            "ability_ids": [self.ability.id],
        })
        first = self.client.post("/api/curriculum/dispatch", data=payload, content_type="application/json")
        second = self.client.post("/api/curriculum/dispatch", data=payload, content_type="application/json")
        self.assertEqual(first.json()["created_count"], 1)
        self.assertEqual(second.json()["created_count"], 0)
        self.assertEqual(second.json()["skipped_count"], 1)
        thread.assert_called_once()

    def test_ai_result_generates_learning_tasks_and_updates_course_match(self):
        payload = {
            "course_name": "工业机器人基础与维护",
            "course_type": "integrated",
            "total_hours": 48,
            "credits": 3,
            "matched_content": "机器人运动学和坐标系变换支撑维护任务。",
            "chapters": [{
                "source_unit_id": self.unit.id,
                "textbook_chapter_id": self.chapter.id,
                "name": "机器人坐标标定任务",
                "task_description": "完成机器人坐标系辨识与标定。",
                "work_scenario": "产线机器人重新部署后的坐标复核。",
                "operation_steps": ["读取坐标参数", "完成坐标变换计算"],
                "safety_points": ["设备运行前确认安全区域"],
                "resource_links": [],
                "knowledge_points": [{
                    "source_point_id": self.point.id,
                    "textbook_node_id": self.knowledge.id,
                    "name": "坐标系变换任务卡",
                    "task_description": "根据工位关系完成坐标转换。",
                    "work_scenario": "机器人末端工具坐标校准。",
                    "operation_steps": ["记录基坐标", "验证转换结果"],
                    "safety_points": ["低速模式验证"],
                    "resource_links": [],
                }],
            }],
        }

        save_ai_course_tree(self.tree, payload)

        self.tree.refresh_from_db()
        self.ability.refresh_from_db()
        self.assertEqual(self.tree.name, "工业机器人基础与维护")
        self.assertEqual(self.tree.nodes.count(), 2)
        self.assertEqual(self.tree.nodes.get(node_type="chapter").textbook_node, self.chapter)
        self.assertEqual(self.tree.nodes.get(node_type="knowledge").textbook_node, self.knowledge)
        self.assertEqual(self.ability.course_matches[0]["course_name"], "工业机器人基础与维护")

    @patch("apps.curriculum.views.threading.Thread")
    def test_ai_generation_endpoint_starts_background_task(self, thread):
        self.client.login(username="course_owner", password="edu@123")

        response = self.client.post(
            f"/api/curriculum/{self.tree.id}/ai-generate",
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["status"], "processing")
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.ai_generation_status, "processing")
        thread.assert_called_once()

    @patch("apps.curriculum.views.threading.Thread")
    def test_ai_regeneration_is_blocked_when_teacher_work_exists(self, thread):
        chapter = CourseTreeNode.objects.create(
            tree=self.tree, node_type="chapter", name="机器人运动学任务",
            source_node=self.unit, textbook_node=self.chapter,
        )
        point = CourseTreeNode.objects.create(
            tree=self.tree, parent=chapter, node_type="knowledge", name="坐标变换任务卡",
            source_node=self.point, textbook_node=self.knowledge,
            is_edited=True,
            resource_links=[{
                "name": "坐标系仿真", "resource_type": "simulation",
                "url": "https://example.edu/simulation/coordinate",
            }],
        )
        CourseQuestion.objects.create(
            node=point, question_type="judgment", stem="工具坐标系需要标定。",
            correct_answer=["正确"], created_by=self.owner,
        )
        self.client.login(username="course_owner", password="edu@123")

        response = self.client.post(
            f"/api/curriculum/{self.tree.id}/ai-generate",
            data=json.dumps({}), content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "teacher_work_protected")
        self.assertEqual(response.json()["details"]["edited_node_count"], 1)
        self.assertEqual(response.json()["details"]["resource_count"], 1)
        self.assertEqual(response.json()["details"]["question_count"], 1)
        self.assertTrue(CourseTreeNode.objects.filter(pk=point.id).exists())
        self.assertTrue(CourseQuestion.objects.filter(node=point).exists())
        thread.assert_not_called()

    def test_save_ai_tree_rechecks_teacher_work_before_overwrite(self):
        chapter = CourseTreeNode.objects.create(
            tree=self.tree, node_type="chapter", name="人工任务",
            source_node=self.unit, textbook_node=self.chapter,
        )
        point = CourseTreeNode.objects.create(
            tree=self.tree, parent=chapter, node_type="knowledge", name="人工任务卡",
            source_node=self.point, textbook_node=self.knowledge, is_edited=True,
        )

        with self.assertRaises(TeacherWorkProtectedError):
            save_ai_course_tree(self.tree, {"chapters": []})

        self.assertTrue(CourseTreeNode.objects.filter(pk=point.id).exists())

    def test_resource_library_api_returns_course_task_tree(self):
        chapter = CourseTreeNode.objects.create(
            tree=self.tree, node_type="chapter", name="机器人运动学任务",
            source_node=self.unit, textbook_node=self.chapter,
        )
        CourseTreeNode.objects.create(
            tree=self.tree, parent=chapter, node_type="knowledge", name="坐标变换任务卡",
            source_node=self.point, textbook_node=self.knowledge,
        )
        self.client.login(username="course_owner", password="edu@123")

        response = self.client.get("/api/curriculum/trees")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["course_count"], 1)
        self.assertEqual(response.json()["courses"][0]["chapters"][0]["points"][0]["name"], "坐标变换任务卡")

    def test_college_manager_can_assign_only_same_college_course_owner(self):
        replacement = User.objects.create_user(username="replacement_owner", password="edu@123")
        UserProfile.objects.create(
            user=replacement, organization=self.organization, role=self.course_role,
        )
        other_org = Organization.objects.create(name="信息工程学院", org_type="学院")
        other_owner = User.objects.create_user(username="other_college_owner", password="edu@123")
        UserProfile.objects.create(
            user=other_owner, organization=other_org, role=self.course_role,
        )
        self.client.login(username="college_manager", password="edu@123")
        candidates = self.client.get(
            f"/api/curriculum/owner-candidates?tree_id={self.tree.id}"
        )
        self.assertEqual(candidates.status_code, 200)
        candidate_ids = [item["id"] for item in candidates.json()["users"]]
        self.assertIn(replacement.id, candidate_ids)
        self.assertNotIn(other_owner.id, candidate_ids)

        rejected = self.client.post(
            f"/api/curriculum/{self.tree.id}/owner",
            data=json.dumps({"owner_id": other_owner.id}),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.owner, self.owner)

        response = self.client.post(
            f"/api/curriculum/{self.tree.id}/owner",
            data=json.dumps({"owner_id": replacement.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.owner, replacement)

        self.client.logout()
        self.client.login(username="course_owner", password="edu@123")
        self.assertEqual(self.client.get("/api/curriculum/trees").json()["courses"], [])

        self.client.logout()
        self.client.login(username="replacement_owner", password="edu@123")
        self.assertEqual(self.client.get("/api/curriculum/trees").json()["stats"]["course_count"], 1)

    def test_college_manager_can_edit_course_details_and_owner_together(self):
        replacement = User.objects.create_user(username="course_editor", password="edu@123")
        UserProfile.objects.create(user=replacement, organization=self.organization, role=self.course_role)
        self.tree.is_published = True
        self.tree.save(update_fields=["is_published", "updated_at"])
        self.client.login(username="college_manager", password="edu@123")
        response = self.client.patch(
            f"/api/curriculum/manage/{self.tree.id}",
            data=json.dumps({
                "name": "工业机器人装调基础", "course_type": "practice",
                "total_hours": 72, "credits": "4.5", "owner_id": replacement.id,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.name, "工业机器人装调基础")
        self.assertEqual(self.tree.course_type, "practice")
        self.assertEqual(self.tree.total_hours, 72)
        self.assertEqual(str(self.tree.credits), "4.5")
        self.assertEqual(self.tree.owner, replacement)
        self.assertFalse(self.tree.is_published)
        self.assertTrue(self.tree.has_unpublished_changes)
        self.assertTrue(response.json()["course"]["republish_required"])

    def test_non_manager_sees_clear_course_management_permission_message(self):
        self.client.login(username="course_owner", password="edu@123")
        response = self.client.get("/课程管理.html")
        self.assertContains(response, "仅学院负责人或超级管理员可以管理课程负责人")

    def test_course_owner_only_sees_assigned_course_trees(self):
        other_tree = CourseTree.objects.create(
            organization=self.organization, textbook=self.textbook,
            name="其他课程", owner=self.manager,
        )
        self.client.login(username="course_owner", password="edu@123")
        response = self.client.get("/api/curriculum/trees")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["courses"]], [self.tree.id])
        other_tree.delete()

    def test_course_owner_can_edit_task_card_and_publish(self):
        chapter = CourseTreeNode.objects.create(
            tree=self.tree, node_type="chapter", name="机器人运动学任务",
            source_node=self.unit, textbook_node=self.chapter,
        )
        point = CourseTreeNode.objects.create(
            tree=self.tree, parent=chapter, node_type="knowledge", name="坐标变换任务卡",
            source_node=self.point, textbook_node=self.knowledge,
        )
        self.client.login(username="course_owner", password="edu@123")
        chapter_response = self.client.post(
            f"/api/curriculum/nodes/{chapter.id}",
            data=json.dumps({
                "task_description": "完成机器人运动学综合学习任务。",
                "work_scenario": "工业机器人工作站坐标标定。",
                "operation_steps": ["分析任务要求", "组织任务实施"],
                "safety_points": ["确认机器人处于安全模式"],
                "resource_links": [],
                "is_edited": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(chapter_response.status_code, 200)
        chapter.refresh_from_db()
        self.assertTrue(chapter.chapter_content_edited)

        response = self.client.post(
            f"/api/curriculum/nodes/{point.id}",
            data=json.dumps({
                "task_description": "完成坐标变换任务。",
                "operation_steps": ["确认基坐标", "验证转换结果"],
                "safety_points": ["低速模式验证"],
                "resource_links": [{
                    "name": "坐标系仿真操作", "resource_type": "simulation",
                    "url": "https://example.edu/simulation/coordinate",
                }],
                "is_edited": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        point.refresh_from_db()
        self.assertTrue(point.is_edited)
        self.assertEqual(point.operation_steps[0], "确认基坐标")
        self.assertEqual(point.resource_links[0]["resource_type"], "simulation")
        chapter.refresh_from_db()
        self.assertTrue(chapter.is_edited)

        publish = self.client.post(f"/api/curriculum/{self.tree.id}/publish")
        self.assertEqual(publish.status_code, 200)
        self.tree.refresh_from_db()
        self.assertTrue(self.tree.is_published)

        # 已发布课程再次编辑时，应自动撤回，待课程负责人重新确认发布。
        response = self.client.post(
            f"/api/curriculum/nodes/{point.id}",
            data=json.dumps({"task_description": "更新后的任务说明", "is_edited": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["republish_required"])
        self.tree.refresh_from_db()
        self.assertFalse(self.tree.is_published)
        self.assertTrue(self.tree.has_unpublished_changes)
        point.refresh_from_db()
        self.assertTrue(point.changed_since_publish)

        tree_data = self.client.get("/api/curriculum/trees").json()["courses"][0]
        self.assertTrue(tree_data["has_unpublished_changes"])
        self.assertTrue(tree_data["chapters"][0]["changed_since_publish"])
        self.assertTrue(tree_data["chapters"][0]["points"][0]["changed_since_publish"])

        republish = self.client.post(f"/api/curriculum/{self.tree.id}/publish")
        self.assertEqual(republish.status_code, 200)
        self.tree.refresh_from_db()
        point.refresh_from_db()
        self.assertTrue(self.tree.is_published)
        self.assertFalse(self.tree.has_unpublished_changes)
        self.assertFalse(point.changed_since_publish)

    def test_publish_precheck_reports_unedited_learning_task(self):
        chapter = CourseTreeNode.objects.create(
            tree=self.tree, node_type="chapter", name="机器人运动学任务",
            source_node=self.unit, textbook_node=self.chapter,
        )
        CourseTreeNode.objects.create(
            tree=self.tree, parent=chapter, node_type="knowledge", name="坐标变换任务卡",
            source_node=self.point, textbook_node=self.knowledge, is_edited=True,
        )
        self.client.login(username="course_owner", password="edu@123")

        response = self.client.post(f"/api/curriculum/{self.tree.id}/publish")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "publish_check_failed")
        self.assertIn("还有 1 个学习任务未编辑确认", response.json()["issues"])
        self.tree.refresh_from_db()
        self.assertFalse(self.tree.is_published)

    def test_course_owner_cannot_read_or_edit_another_owners_node(self):
        other_tree = CourseTree.objects.create(
            organization=self.organization, textbook=self.textbook,
            name="其他教师课程", owner=self.manager,
        )
        other_node = CourseTreeNode.objects.create(
            tree=other_tree, node_type="chapter", name="其他教师学习任务",
        )
        self.client.login(username="course_owner", password="edu@123")

        read_response = self.client.get(f"/api/curriculum/nodes/{other_node.id}")
        edit_response = self.client.post(
            f"/api/curriculum/nodes/{other_node.id}",
            data=json.dumps({"name": "越权修改", "is_edited": True}),
            content_type="application/json",
        )
        publish_response = self.client.post(
            f"/api/curriculum/{other_tree.id}/publish"
        )

        self.assertEqual(read_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(publish_response.status_code, 403)
        other_node.refresh_from_db()
        self.assertEqual(other_node.name, "其他教师学习任务")

    def test_unassigned_ability_cannot_be_dispatched(self):
        self.ability.organization = None
        self.ability.save(update_fields=["organization", "updated_at"])
        self.client.login(username="capability_manager", password="edu@123")
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

    def test_authenticated_user_without_dispatch_permission_is_forbidden(self):
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

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "capability_dispatch_forbidden")
        self.assertFalse(CourseTree.objects.filter(
            organization=self.organization, source_ability=self.ability,
        ).exists())
