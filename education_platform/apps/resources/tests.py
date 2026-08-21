from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import Organization

from .models import Textbook, TextbookNode


class TextbookNodeModelTests(TestCase):
    def setUp(self):
        organization = Organization.objects.create(name="智能制造学院", org_type="学院")
        self.textbook = Textbook.objects.create(
            organization=organization,
            name="数据库应用基础",
        )
        self.chapter = TextbookNode.objects.create(
            textbook=self.textbook,
            node_type="chapter",
            name="数据库安全",
        )

    def test_knowledge_point_can_belong_to_chapter(self):
        node = TextbookNode(
            textbook=self.textbook,
            parent=self.chapter,
            node_type="knowledge",
            name="数据库权限",
        )
        node.full_clean()

    def test_section_level_is_not_supported(self):
        node = TextbookNode(
            textbook=self.textbook,
            parent=self.chapter,
            node_type="section",
            name="不应存在的节",
        )
        with self.assertRaises(ValidationError):
            node.full_clean()
