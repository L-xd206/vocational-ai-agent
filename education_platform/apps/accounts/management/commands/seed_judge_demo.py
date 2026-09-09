"""初始化比赛评审用的端到端演示场景。

用法：python manage.py seed_judge_demo

该命令会归档旧的产业链和岗位，仅在前台展示一条
“智能制造 → 数控操作工”的评审主线。可以安全重复执行。
"""

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Permission, Role, UserProfile
from apps.capabilities.models import AbilityMap, CapabilityNode
from apps.capabilities.services import serialize_official_tree
from apps.collection.models import CrawlSource, CrawlTask, JobListing
from apps.collection.services import create_analysis_batch
from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.industry.models import Chain, Job
from apps.learning.models import LearningPlan, LearningRecord
from apps.organizations.models import Organization, Student
from apps.resources.models import Textbook, TextbookNode
from apps.teaching.models import CourseQuestion


DEMO_TREE = [
    {
        "name": "作业安全与现场准备",
        "college": "智能制造学院",
        "units": [
            {
                "name": "安全装置与防护检查",
                "children": [
                    {"name": "确认急停、安全门和安全光栅功能有效"},
                    {"name": "检查个人防护用品与作业区域状态"},
                ],
            },
            {
                "name": "工作站上电准备",
                "children": [
                    {"name": "核对工装、工件和末端执行器状态"},
                    {"name": "完成控制柜上电前检查与风险确认"},
                ],
            },
        ],
    },
    {
        "name": "工业机器人系统安装与调试",
        "college": "智能制造学院",
        "units": [
            {
                "name": "机械与电气连接",
                "children": [
                    {"name": "识读机器人工作站电气原理图"},
                    {"name": "完成末端执行器和传感器接线检查"},
                ],
            },
            {
                "name": "示教与程序调试",
                "children": [
                    {"name": "完成坐标系标定和示教点设置"},
                    {"name": "调试运动轨迹并验证节拍要求"},
                ],
            },
        ],
    },
    {
        "name": "自动化产线运行与故障诊断",
        "college": "智能制造学院",
        "units": [
            {
                "name": "产线运行监控",
                "children": [
                    {"name": "监控机器人、PLC和输送线运行状态"},
                    {"name": "识别产线节拍异常和质量报警信息"},
                ],
            },
            {
                "name": "常见故障诊断",
                "children": [
                    {"name": "依据报警代码定位安全回路故障"},
                    {"name": "完成I/O信号与通信异常排查"},
                ],
            },
        ],
    },
    {
        "name": "预防性维护与运行数据管理",
        "college": "智能制造学院",
        "units": [
            {
                "name": "设备点检与维护",
                "children": [
                    {"name": "执行机器人本体、线缆和控制柜日常点检"},
                    {"name": "完成程序备份、电池检查和维护记录"},
                ],
            },
            {
                "name": "运行数据记录与交接",
                "children": [
                    {"name": "记录产量、停机原因和故障处理过程"},
                    {"name": "完成设备状态和程序版本交接确认"},
                ],
            },
        ],
    },
]


class Command(BaseCommand):
    help = "初始化比赛评审用的智能制造岗位能力图谱演示数据（可重复执行）"

    @transaction.atomic
    def handle(self, *args, **options):
        college = self._ensure_college()
        self._ensure_roles_and_accounts(college)
        job = self._prepare_industry_and_job()
        crawl_task = self._prepare_listings(job)
        ability_nodes = self._prepare_capability_tree(job)
        self._prepare_candidate_tree(job, crawl_task)
        course_tree = self._prepare_course_tree(college, ability_nodes)
        self._prepare_student_experience(course_tree)

        self.stdout.write(self.style.SUCCESS(
            "评审演示数据已就绪：智能制造 / 数控操作工 / "
            "8 项岗位能力 / 51 个知识点技能点 / 1 门课程 / 4 道试题。"
        ))

    def _ensure_college(self):
        return Organization.objects.filter(
            name="智能制造学院", org_type="学院", is_enabled=True
        ).order_by("id").first() or Organization.objects.create(
            name="智能制造学院",
            org_type="学院",
            description="比赛评审演示使用的学院组织。",
        )

    def _ensure_roles_and_accounts(self, college):
        capability_permissions = Permission.objects.filter(code__in=[
            "job_collection", "capability_graph", "capability_dispatch", "profile", "message",
        ])
        group_role, _ = Role.objects.get_or_create(
            name="专业群负责人",
            defaults={"description": "维护产业链、岗位和岗位数据采集", "is_builtin": True},
        )
        group_role.permissions.set(capability_permissions)
        major_role, _ = Role.objects.get_or_create(
            name="专业负责人",
            defaults={"description": "审核岗位能力树并向学院下发", "is_builtin": True},
        )
        major_role.permissions.set(capability_permissions)

        User = get_user_model()
        for username, real_name, role, bio in [
            ("major_group_lead", "专业群负责人", group_role, "负责智能制造产业链与岗位需求分析"),
            ("major_lead", "专业负责人", major_role, "负责工业机器人系统运维员岗位能力审核"),
        ]:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password("edu@123")
                user.save(update_fields=["password"])
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.real_name = real_name
            profile.role = role
            profile.organization = college
            profile.bio = bio
            profile.save()

    def _prepare_industry_and_job(self):
        # 归档旧的展示数据；历史记录仍保留在数据库中，不影响历史追溯。
        Chain.objects.update(is_enabled=False)
        Job.objects.update(is_enabled=False)

        chain, _ = Chain.objects.get_or_create(
            name="智能制造",
            defaults={
                "description": "面向智能制造专业群的数控操作工岗位能力分析场景。",
                "is_enabled": True,
            },
        )
        chain.description = "面向智能制造专业群的数控操作工岗位能力分析场景。"
        chain.is_enabled = True
        chain.save(update_fields=["description", "is_enabled"])

        job, _ = Job.objects.get_or_create(
            chain=chain,
            name="数控操作工",
            defaults={
                "aliases": ["CNC操作员", "加工中心操作员", "数控车床操作员"],
                "search_keywords": ["数控操作工", "CNC操作员", "加工中心操作员"],
                "is_confirmed": True,
                "is_enabled": True,
            },
        )
        job.aliases = ["CNC操作员", "加工中心操作员", "数控车床操作员"]
        job.search_keywords = ["数控操作工", "CNC操作员", "加工中心操作员"]
        job.is_confirmed = True
        job.is_enabled = True
        job.save(update_fields=["aliases", "search_keywords", "is_confirmed", "is_enabled"])
        return job

    def _prepare_listings(self, job):
        JobListing.objects.filter(job=job).delete()
        CrawlTask.objects.filter(job=job).delete()
        source, _ = CrawlSource.objects.get_or_create(
            code="mohrss",
            defaults={
                "name": "中国公共招聘网",
                "base_url": "http://job.mohrss.gov.cn",
                "interval_minutes": 1440,
                "is_enabled": False,
            },
        )
        source.name = "中国公共招聘网"
        source.base_url = "http://job.mohrss.gov.cn"
        CrawlSource.objects.exclude(pk=source.pk).update(is_enabled=False)
        source.is_enabled = True
        data_path = Path(settings.BASE_DIR) / "data" / "智能制造_数控操作工_爬取结果.json"
        if not data_path.exists():
            raise RuntimeError(f"缺少评审演示招聘数据文件：{data_path}")
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        results = payload.get("results", [])
        if len(results) < 10:
            raise RuntimeError("评审演示招聘数据不足 10 条，无法生成岗位能力图谱")
        now = timezone.now()
        source.last_run_at = now
        source.next_run_at = now + timedelta(minutes=source.interval_minutes)
        source.save(update_fields=["name", "base_url", "is_enabled", "last_run_at", "next_run_at", "updated_at"])
        task = CrawlTask.objects.create(
            job=job,
            source=source,
            trigger_type="scheduled",
            status="completed",
            total_keywords=len(job.search_keywords),
            total_results=len(results),
            new_results=len(results),
            scheduled_at=now - timedelta(minutes=5),
            started_at=now,
            finished_at=now,
        )
        JobListing.objects.bulk_create([
            JobListing(
                task=task,
                job=job,
                crawl_source=source,
                title=str(item.get("title") or "数控操作工"),
                company=str(item.get("company") or "公开招聘企业"),
                city=str(item.get("city") or ""),
                salary=str(item.get("salary") or ""),
                education=str(item.get("education") or ""),
                requirements=str(item.get("requirements") or ""),
                headcount=str(item.get("headcount") or ""),
                post_date=str(item.get("date") or ""),
                source=str(item.get("source") or "公开招聘信息脱敏样本"),
                source_url="https://example.edu/judge-demo",
                raw_json={"demo": True, "note": "用于比赛评审体验的公开招聘信息脱敏样本", "source_item": item},
            )
            for item in results
        ])
        return task

    def _prepare_capability_tree(self, job):
        tree = serialize_official_tree(job)
        if len(tree) != 8:
            raise RuntimeError("数控操作工正式能力树不完整，请先恢复 8 项岗位能力的演示数据")
        ability_map, _ = AbilityMap.objects.get_or_create(job=job)
        ability_map.abilities_json = tree
        ability_map.total_abilities = len(tree)
        ability_map.total_skills = sum(len(unit.get("children", [])) for ability in tree for unit in ability.get("units", []))
        ability_map.raw_text = "评审演示数据：根据公开招聘信息脱敏样本生成，已由专业负责人审核确认。"
        ability_map.generation_status = "ready"
        ability_map.generation_error = ""
        ability_map.review_status = "confirmed"
        ability_map.review_note = "专业负责人已审核：能力树可下发至智能制造学院用于课程建设。"
        ability_map.reviewed_at = timezone.now()
        ability_map.save()
        return {
            node.name: node
            for node in CapabilityNode.objects.filter(job=job, node_type="ability", parent__isnull=True)
        }

    def _prepare_candidate_tree(self, job, crawl_task):
        """预置一组待专业负责人确认的 AI 增量候选节点。"""
        job.analysis_batches.all().delete()
        candidate_tree = [{
            "name": "设备维护与精度保障",
            "college": "智能制造学院",
            "units": [{
                "name": "机床日常维护保养",
                "children": [
                    {"name": "使用数字化点检表记录主轴、导轨与润滑状态", "evidence": "招聘要求[8]、[12]"},
                    {"name": "根据设备运行数据提出预防性维护建议", "evidence": "招聘要求[7]、[12]"},
                    {"name": "核对数控系统参数备份与程序版本", "evidence": "招聘要求[8]"},
                    {"name": "使用手机拍摄机床运行视频作为日常点检记录", "evidence": "招聘要求[19]"},
                ],
            }],
        }]
        batch = create_analysis_batch(
            job,
            candidate_tree,
            crawl_task=crawl_task,
            model_name="评审演示 AI 分析",
            raw_ai_output="基于数控操作工公开招聘信息脱敏样本生成的待审核增量候选节点。",
        )
        rejected = batch.nodes.get(name="使用手机拍摄机床运行视频作为日常点检记录")
        rejected.decision_status = "rejected"
        rejected.decision_note = "与岗位核心能力关联较弱，且不宜将手机拍摄作为规范点检方法。"
        rejected.decided_at = timezone.now()
        rejected.save(update_fields=["decision_status", "decision_note", "decided_at", "updated_at"])

    def _prepare_course_tree(self, college, ability_nodes):
        CourseTree.objects.filter(name__in=["数控加工工艺与编程", "工业机器人工作站运维与调试"]).delete()
        source_ability = ability_nodes["加工准备与工程识图"]
        owner = get_user_model().objects.get(username="course_owner")
        textbook = Textbook.objects.filter(
            organization=college,
            name__contains="数控加工工艺与编程",
        ).first()
        if textbook is None:
            raise RuntimeError("缺少《数控加工工艺与编程》教材知识库，请先执行 python manage.py seed")

        chapter_mapping = {
            "零件图纸阅读与分析": "第二章 数控加工的工艺基础",
            "加工工艺方案制定": "第二章 数控加工的工艺基础",
            "夹具选择与装夹方案设计": "第一章 数控加工的切削基础",
        }
        knowledge_mapping = {
            "识读零件图标题栏、尺寸标注与技术要求": "零件图与工艺分析",
            "开展零件结构工艺性分析": "加工方法选择",
            "确认毛坯材料与余量": "零件毛坯的选择",
            "划分工序并制定加工路线": "工艺路线的拟定",
            "选择刀具并制定切削参数": "设备、刀具、夹具和量具选择",
            "选择适配的夹具与定位方式": "夹具选择原则",
            "完成工件装夹、找正与夹紧检查": "工件夹紧要求与夹紧力",
        }
        required_names = set(chapter_mapping.values()) | set(knowledge_mapping.values())
        textbook_nodes = {
            node.name: node
            for node in TextbookNode.objects.filter(textbook=textbook, name__in=required_names)
        }
        missing_names = required_names - textbook_nodes.keys()
        if missing_names:
            raise RuntimeError(f"教材知识库缺少演示映射节点：{', '.join(sorted(missing_names))}")

        course_tree, _ = CourseTree.objects.update_or_create(
            organization=college,
            source_ability=source_ability,
            defaults={
                "textbook": textbook,
                "name": "数控加工工艺与编程",
                "course_type": "integrated",
                "total_hours": 64,
                "credits": 4.0,
                "owner": owner,
                "source_snapshot": {
                    "ability": source_ability.name,
                    "scenario": "数控零件加工工艺设计与编程",
                    "textbook": textbook.name,
                },
                "is_published": True,
                "published_at": timezone.now(),
                "ai_generation_status": "ready",
                "has_manual_edits": True,
                "has_unpublished_changes": False,
                "created_by": owner,
            },
        )
        course_tree.nodes.all().delete()
        knowledge_nodes = []
        for unit_order, unit in enumerate(source_ability.children.filter(node_type="unit").order_by("sort_order", "id")):
            chapter = CourseTreeNode.objects.create(
                tree=course_tree,
                node_type="chapter",
                name=unit.name,
                source_node=unit,
                textbook_node=textbook_nodes[chapter_mapping[unit.name]],
                task_description=f"完成“{unit.name}”相关的现场操作与记录任务。",
                work_scenario="数控零件图纸分析、加工工艺制定与装夹方案设计。",
                operation_steps=["确认作业安全条件", "执行规定操作", "记录并复核结果"],
                safety_points=["执行机床安全操作规程", "确认工件装夹和刀具状态后再启动机床"],
                is_edited=True,
                chapter_content_edited=True,
                sort_order=unit_order,
            )
            for point_order, point in enumerate(unit.children.filter(node_type="point").order_by("sort_order", "id")):
                knowledge_nodes.append(CourseTreeNode.objects.create(
                    tree=course_tree,
                    parent=chapter,
                    node_type="knowledge",
                    name=point.name,
                    source_node=point,
                    textbook_node=textbook_nodes[knowledge_mapping[point.name]],
                    task_description=f"掌握并能够完成：{point.name}。",
                    is_edited=True,
                    sort_order=point_order,
                ))
        self._prepare_questions(knowledge_nodes, owner)
        return course_tree

    def _prepare_questions(self, knowledge_nodes, owner):
        questions = [
            ("single", "数控加工前，确认毛坯材料与加工余量的主要目的是什么？", ["A. 保证加工工艺和切削参数选择正确", "B. 使程序名称更简短", "C. 取消尺寸检测", "D. 不需要查看图纸"], ["A"], "easy"),
            ("judgment", "工件装夹完成后，可以不检查找正和夹紧状态，直接启动数控机床。", [], ["错误"], "easy"),
            ("single", "制定数控加工路线时，首先应依据什么？", ["A. 零件图纸、技术要求和毛坯情况", "B. 操作者个人习惯", "C. 任意选择刀具", "D. 只看加工时间"], ["A"], "medium"),
            ("short", "请简述数控加工前阅读零件图纸时需要重点确认的内容。", [], ["确认标题栏、材料、尺寸、公差、表面粗糙度、形位公差和技术要求，并结合毛坯情况进行工艺分析。"], "medium"),
        ]
        for index, (question_type, stem, options, answer, difficulty) in enumerate(questions):
            CourseQuestion.objects.create(
                node=knowledge_nodes[index % len(knowledge_nodes)],
                question_type=question_type,
                stem=stem,
                options=options,
                correct_answer=answer,
                analysis="评审演示题：用于验证学生对数控加工工艺、图纸识读、刀具选择与安全操作要点的掌握情况。",
                difficulty=difficulty,
                sort_order=index,
                created_by=owner,
            )

    def _prepare_student_experience(self, course_tree):
        student = Student.objects.select_related("user").filter(user__username="student").first()
        if student is None:
            raise RuntimeError("未找到 student 演示账号对应的学生档案，请先执行 python manage.py seed")
        student.major = "数控技术"
        student.grade = "2024级"
        student.save(update_fields=["major", "grade", "updated_at"])
        # 本命令仅用于评审演示账号，因此清空该账号的旧样例，避免学生端展示多条不相关主线。
        LearningPlan.objects.filter(student=student).delete()
        LearningPlan.objects.update_or_create(
            student=student,
            course_tree=course_tree,
            plan_type="semester",
            defaults={
                "name": "数控加工工艺与编程学习计划",
                "category": "岗位能力学习",
                "status": "doing",
                "progress": 40,
                "learned_hours": 18,
                "total_hours": 64,
                "deadline": timezone.localdate().replace(month=12, day=31),
                "teacher": "刘老师",
            },
        )
        LearningRecord.objects.filter(student=student).delete()
        LearningRecord.objects.bulk_create([
            LearningRecord(student=student, title="已接收岗位能力学习计划", description="课程负责人已发布数控加工工艺与编程学习任务。", tag="评审演示"),
            LearningRecord(student=student, title="完成零件图纸阅读练习", description="已完成图纸标题栏、尺寸标注和技术要求识读任务，等待教师评价。", tag="评审演示"),
        ])
