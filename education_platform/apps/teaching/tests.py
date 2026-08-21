from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.organizations.models import Organization
from apps.resources.models import Textbook

from .models import CourseQuestion


class CourseQuestionModelTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="智能制造学院", org_type="学院")
        textbook = Textbook.objects.create(organization=organization, name="工业机器人技术基础")
        tree = CourseTree.objects.create(
            organization=organization,
            textbook=textbook,
            name="工业机器人技术基础",
        )
        self.chapter = CourseTreeNode.objects.create(
            tree=tree,
            node_type="chapter",
            name="机器人基础",
        )
        self.knowledge = CourseTreeNode.objects.create(
            tree=tree,
            parent=self.chapter,
            node_type="knowledge",
            name="机器人定义与分类",
        )

    def test_question_can_only_attach_to_knowledge_node(self):
        question = CourseQuestion(
            node=self.chapter,
            question_type="judgment",
            stem="工业机器人属于自动化装备。",
            correct_answer=[True],
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_choice_question_requires_options(self):
        question = CourseQuestion(
            node=self.knowledge,
            question_type="single",
            stem="以下哪项属于工业机器人？",
            correct_answer=["A"],
        )
        with self.assertRaises(ValidationError):
            question.full_clean()
