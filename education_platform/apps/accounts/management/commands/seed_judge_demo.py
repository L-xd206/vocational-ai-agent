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
from django.core.management import call_command
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
from apps.learning.models import (
    LearningPlan, LearningProgress, LearningRecord, PlanCourse, PlanPoint,
)
from apps.organizations.models import Organization, Student
from apps.resources.models import Textbook, TextbookNode
from apps.teaching.models import CourseQuestion


CNC_DEMO_TREE = [
    {
        "name": "加工准备与工程识图",
        "college": "智能制造学院",
        "units": [
            {
                "name": "零件图纸阅读与分析",
                "children": [
                    {"name": "识读零件图标题栏、尺寸标注与技术要求"},
                    {"name": "开展零件结构工艺性分析"},
                ],
            },
            {
                "name": "加工工艺方案制定",
                "children": [
                    {"name": "确认毛坯材料与余量"},
                    {"name": "划分工序并制定加工路线"},
                    {"name": "选择刀具并制定切削参数"},
                ],
            },
            {
                "name": "夹具选择与装夹方案设计",
                "children": [
                    {"name": "选择适配的夹具与定位方式"},
                    {"name": "完成工件装夹、找正与夹紧检查"},
                ],
            },
        ],
    },
    {
        "name": "刀具准备与对刀操作",
        "college": "智能制造学院",
        "units": [
            {
                "name": "刀具安装与刀补设置",
                "children": [
                    {"name": "完成刀具与刀柄装配"},
                    {"name": "完成刀具安装、测量与刀具补偿设置"},
                ],
            },
            {
                "name": "工件坐标系建立与对刀",
                "children": [
                    {"name": "完成X、Y方向对刀"},
                    {"name": "完成Z向对刀与刀长补偿设置"},
                    {"name": "验证对刀结果与坐标系安全性"},
                ],
            },
        ],
    },
    {
        "name": "数控编程与程序校验",
        "college": "智能制造学院",
        "units": [
            {
                "name": "手工程序编制",
                "children": [
                    {"name": "编写基本G代码程序"},
                    {"name": "应用M代码、子程序与循环指令"},
                ],
            },
            {
                "name": "程序输入与校验",
                "children": [
                    {"name": "完成数控程序输入与编辑"},
                    {"name": "使用单段运行和空运行校验程序"},
                ],
            },
            {
                "name": "CAM自动编程与验证",
                "children": [
                    {"name": "使用CAM软件生成刀路与NC程序"},
                    {"name": "通过仿真校验识别碰撞、过切与参数风险"},
                ],
            },
        ],
    },
    {
        "name": "数控机床操作与零件加工",
        "college": "智能制造学院",
        "units": [
            {
                "name": "机床启动与基本操作",
                "children": [
                    {"name": "完成开机前安全检查"},
                    {"name": "使用操作面板完成机床基本控制"},
                ],
            },
            {
                "name": "数控车削加工",
                "children": [
                    {"name": "完成外圆与端面车削"},
                    {"name": "完成槽、螺纹与孔类车削"},
                ],
            },
            {
                "name": "加工中心铣削加工",
                "children": [
                    {"name": "完成平面与轮廓铣削"},
                    {"name": "完成型腔与复杂曲面加工"},
                    {"name": "完成孔系加工"},
                ],
            },
        ],
    },
    {"name": "加工过程监控与质量控制", "college": "智能制造学院", "units": [
        {"name": "加工状态过程监控", "children": [{"name": "监控切削声音、振动与刀具状态"}, {"name": "检查并调整冷却液与润滑状态"}]},
        {"name": "加工质量巡检", "children": [{"name": "依据工艺要求执行首件与过程巡检"}, {"name": "根据检测结果修正加工参数"}]},
        {"name": "质量检测与数据分析", "children": [{"name": "使用游标卡尺、千分尺和百分表检测"}, {"name": "完成表面粗糙度与形位误差检查"}, {"name": "利用SPC数据与控制图判断质量趋势"}]},
    ]},
    {"name": "设备维护与精度保障", "college": "智能制造学院", "units": [
        {"name": "机床日常维护保养", "children": [{"name": "执行清洁、6S与导轨点检"}, {"name": "检查润滑系统与冷却液"}, {"name": "执行点、温、振等保养记录"}]},
        {"name": "机床几何精度检测", "children": [{"name": "完成水平、平行度与垂直度检测"}, {"name": "检测定位精度与反向间隙"}]},
        {"name": "系统数据备份与精度补偿", "children": [{"name": "完成NC、PMC及参数数据备份与恢复"}, {"name": "实施丝杠误差补偿并复核"}]},
    ]},
    {"name": "故障诊断与异常处理", "college": "智能制造学院", "units": [
        {"name": "加工质量异常诊断", "children": [{"name": "分析尺寸超差与表面质量问题"}, {"name": "处理振纹、崩刃与排屑异常"}]},
        {"name": "设备报警与PMC诊断", "children": [{"name": "依据数控系统报警信息定位故障"}, {"name": "使用PMC梯形图与信号追踪诊断"}]},
        {"name": "机械故障与应急处置", "children": [{"name": "处理卡刀、碰撞与突然断电"}, {"name": "执行停机隔离并完成异常上报"}]},
    ]},
    {"name": "安全生产与职业素养", "college": "智能制造学院", "units": [
        {"name": "安全生产操作", "children": [{"name": "遵守数控机床安全操作规程"}, {"name": "正确使用个人防护用品和安全装置"}]},
        {"name": "质量意识与规范作业", "children": [{"name": "按工艺文件和检验规范实施作业"}, {"name": "保持现场6S并执行质量追溯"}]},
        {"name": "团队协作与工艺文件", "children": [{"name": "完成班组交接与异常协同处理"}, {"name": "填写加工记录并提出效率改进建议"}]},
    ]},
]


class Command(BaseCommand):
    help = "初始化比赛评审用的智能制造岗位能力图谱演示数据（可重复执行）"

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_organizations", verbosity=0)
        call_command("seed_accounts", verbosity=0)
        college = self._ensure_college()
        self._ensure_roles_and_accounts(college)
        job = self._prepare_industry_and_job()
        self._prepare_official_nodes(job, college)
        self._prepare_textbook(college)
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
        colleges = Organization.objects.filter(
            name="智能制造学院", org_type="学院", is_enabled=True
        )
        # 旧演示数据库可能保留一个没有上级学校的同名学院。优先使用
        # seed_organizations 创建的正式学院，避免课程与账号看似同院、实际 ID 不同。
        college = colleges.filter(parent__isnull=False).order_by("id").first()
        return college or colleges.order_by("id").first() or Organization.objects.create(
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
            ("major_lead", "专业负责人", major_role, "负责数控操作工岗位能力审核与学院下发"),
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

        # 一键启动必须兼容已存在的旧数据库：统一所有评审账号的学院归属，
        # 保证课程负责人的可见范围与课程树所属学院完全一致。
        UserProfile.objects.filter(user__username__in=[
            "college_manager", "course_owner", "course_owner_b", "teacher", "student",
        ]).update(organization=college)

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

    def _prepare_official_nodes(self, job, college):
        """构建可独立复现的 8 项能力、51 个知识点/技能点正式树。"""
        CapabilityNode.objects.filter(job=job).delete()
        for ability_order, ability_data in enumerate(CNC_DEMO_TREE):
            ability = CapabilityNode.objects.create(
                job=job,
                node_type="ability",
                name=ability_data["name"],
                organization=college,
                origin="ai",
                sort_order=ability_order,
            )
            for unit_order, unit_data in enumerate(ability_data["units"]):
                unit = CapabilityNode.objects.create(
                    job=job,
                    parent=ability,
                    node_type="unit",
                    name=unit_data["name"],
                    organization=college,
                    origin="ai",
                    sort_order=unit_order,
                )
                for point_order, point_data in enumerate(unit_data["children"]):
                    CapabilityNode.objects.create(
                        job=job,
                        parent=unit,
                        node_type="point",
                        name=point_data["name"],
                        organization=college,
                        origin="ai",
                        sort_order=point_order,
                    )

    def _prepare_textbook(self, college):
        """准备课程转化所需的最小教材知识库。"""
        owner = get_user_model().objects.get(username="course_owner")
        textbook, _ = Textbook.objects.update_or_create(
            organization=college,
            name="数控加工工艺与编程",
            edition="评审演示版",
            defaults={
                "publisher": "职业教育数字资源中心",
                "raw_text": "用于评审演示的脱敏课程知识结构。",
                "created_by": owner,
            },
        )
        textbook.nodes.all().delete()
        chapters = [
            ("第一章 数控加工的切削基础", [
                "设备、刀具、夹具和量具选择", "夹具选择原则", "工件夹紧要求与夹紧力",
            ]),
            ("第二章 数控加工的工艺基础", [
                "零件图与工艺分析", "加工方法选择", "零件毛坯的选择", "工艺路线的拟定",
            ]),
        ]
        for chapter_order, (chapter_name, knowledge_names) in enumerate(chapters):
            chapter = TextbookNode.objects.create(
                textbook=textbook,
                node_type="chapter",
                name=chapter_name,
                sort_order=chapter_order,
            )
            for knowledge_order, knowledge_name in enumerate(knowledge_names):
                TextbookNode.objects.create(
                    textbook=textbook,
                    parent=chapter,
                    node_type="knowledge",
                    name=knowledge_name,
                    content=f"{knowledge_name}的教学要点与操作规范。",
                    sort_order=knowledge_order,
                )

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
        # 启动后约 2 分钟完成首次调度，之后按每日周期运行，避免反复生成重复任务。
        source.interval_minutes = 1440
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
        source.next_run_at = now + timedelta(minutes=2)
        source.save(update_fields=["name", "base_url", "interval_minutes", "is_enabled", "last_run_at", "next_run_at", "updated_at"])
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
                    resource_links=[
                        f"《数控加工工艺与编程》评审演示教材：{knowledge_mapping[point.name]}",
                        f"{unit.name}课堂操作指导单",
                    ],
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
            student_user = get_user_model().objects.get(username="student")
            student = Student.objects.filter(name="张晨希").first() or Student.objects.first()
            if student is None:
                raise RuntimeError("未找到可用于评审演示的学生档案")
            student.user = student_user
        student.major = "数控技术"
        student.grade = "2024级"
        student.save(update_fields=["user", "major", "grade", "updated_at"])
        # 本命令仅用于评审演示账号，因此清空该账号的旧样例，避免学生端展示多条不相关主线。
        LearningPlan.objects.filter(student=student).delete()
        plan, _ = LearningPlan.objects.update_or_create(
            student=student,
            name="数控加工工艺与编程学习计划",
            plan_type="semester",
            defaults={
                "category": "岗位能力学习",
                "status": "doing",
                "progress": 29,
                "learned_hours": 19,
                "total_hours": 64,
                "deadline": timezone.localdate().replace(month=12, day=31),
                "teacher": "刘老师",
            },
        )
        plan_course, _ = PlanCourse.objects.update_or_create(
            plan=plan,
            course_tree=course_tree,
            defaults={"sort_order": 0},
        )
        # 学期计划默认包含该课程全部 7 个任务卡，并预置 2 个已完成节点。
        # 评委既能看到已有学习成果，也能继续标记剩余任务完成。
        point_nodes = list(course_tree.nodes.filter(
            node_type="knowledge",
        ).order_by("parent__sort_order", "sort_order", "id"))
        PlanPoint.objects.filter(plan_course=plan_course).delete()
        PlanPoint.objects.bulk_create([
            PlanPoint(plan_course=plan_course, node=node, sort_order=index)
            for index, node in enumerate(point_nodes)
        ])
        LearningProgress.objects.filter(student=student, node__tree=course_tree).delete()
        LearningProgress.objects.bulk_create([
            LearningProgress(student=student, node=node)
            for node in point_nodes[:2]
        ])
        LearningRecord.objects.filter(student=student).delete()
        LearningRecord.objects.bulk_create([
            LearningRecord(student=student, title="已接收岗位能力学习计划", description="课程负责人已发布数控加工工艺与编程学习任务。", tag="评审演示"),
            LearningRecord(student=student, title="完成零件图纸阅读练习", description="已完成图纸标题栏、尺寸标注和技术要求识读任务，等待教师评价。", tag="评审演示"),
        ])
