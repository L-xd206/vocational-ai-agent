"""准备比赛演示所需的数控操作工完整业务数据。

用法：python manage.py seed_competition_demo

命令可重复执行：招聘记录按内容去重，其余业务数据按稳定名称更新。
"""

import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.collection.models import CrawlSource, CrawlTask, JobListing
from apps.collection.services import save_crawl_result
from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.curriculum.services import build_ability_snapshot
from apps.industry.models import Job
from apps.learning.models import LearningPlan, LearningRecord
from apps.organizations.models import Class, Student
from apps.resources.models import Textbook
from apps.teaching.models import CourseQuestion, TeachingArrangement


class Command(BaseCommand):
    help = "准备数控操作工比赛演示数据（招聘→能力→课程→教学→学生）"

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        job = Job.objects.filter(name="数控操作工", chain__name="智能制造").first()
        if job is None:
            raise CommandError("未找到“智能制造 / 数控操作工”岗位")

        source = CrawlSource.objects.filter(code="mohrss").first()
        if source is None:
            raise CommandError("未找到中国公共招聘网采集源，请先执行 migrate")

        data_file = Path(settings.BASE_DIR) / "data" / "智能制造_数控操作工_爬取结果.json"
        if not data_file.exists():
            raise CommandError(f"缺少演示招聘数据文件：{data_file}")
        payload = json.loads(data_file.read_text(encoding="utf-8"))
        results = payload.get("results") or []
        if not results:
            raise CommandError("数控操作工演示招聘数据为空")

        now = timezone.now()
        task = CrawlTask.objects.filter(
            job=job,
            source=source,
            trigger_type="scheduled",
            error_message="比赛演示：后台定时采集",
        ).order_by("id").first()
        if task is None:
            task = CrawlTask.objects.create(
                job=job,
                source=source,
                trigger_type="scheduled",
                status="completed",
                error_message="比赛演示：后台定时采集",
            )

        task.status = "completed"
        task.total_keywords = len(payload.get("keywords_used") or job.search_keywords or [job.name])
        task.total_results = len(results)
        task.scheduled_at = now - timedelta(minutes=3)
        task.started_at = now - timedelta(minutes=2)
        task.finished_at = now - timedelta(minutes=1)
        task.results_json = results
        task.save()

        created_count = 0
        for raw_item in results:
            item = dict(raw_item)
            for key in ("title", "company", "city", "salary", "education", "headcount", "date", "source"):
                item[key] = str(item.get(key, "") or "")
            item.setdefault("source_url", source.base_url)
            _, created = save_crawl_result(task, item)
            created_count += int(created)

        # 重复执行命令时保留这次演示任务首次导入的新增量，避免页面把同一批
        # 比赛数据误显示成“新增 0 条”。
        task.new_results = max(task.new_results, created_count)
        task.save(update_fields=["new_results"])
        source.last_run_at = task.finished_at
        source.next_run_at = now + timedelta(minutes=source.interval_minutes)
        source.save(update_fields=["last_run_at", "next_run_at", "updated_at"])

        ability = job.capability_nodes.filter(
            node_type="ability",
            name="加工准备与工程识图",
        ).first()
        if ability is None:
            raise CommandError("数控操作工正式能力树中缺少“加工准备与工程识图”")

        college = ability.organization
        if college is None:
            raise CommandError("“加工准备与工程识图”尚未分配学院")
        textbook = Textbook.objects.filter(
            organization=college,
            name__startswith="数控加工工艺与编程",
        ).first()
        if textbook is None:
            raise CommandError("学院教材库中缺少《数控加工工艺与编程》")

        course_owner = User.objects.filter(username="course_owner").first()
        teacher = User.objects.filter(username="teacher").first()
        student_user = User.objects.filter(username="student").first()
        admin = User.objects.filter(username="admin").first()
        if not all([course_owner, teacher, student_user]):
            raise CommandError("缺少 course_owner、teacher 或 student 演示账号，请先执行 seed")

        course = CourseTree.objects.filter(name="数控加工工艺与编程").first()
        if course is None:
            raise CommandError("未找到已经生成的《数控加工工艺与编程》课程树")
        course.organization = college
        course.textbook = textbook
        course.source_ability = ability
        course.source_snapshot = build_ability_snapshot(ability)
        course.owner = course_owner
        course.created_by = admin
        course.course_type = "integrated"
        course.total_hours = 64
        course.credits = 4
        course.ai_generation_status = "ready"
        course.ai_generation_error = ""
        course.is_published = True
        course.published_at = course.published_at or now
        course.has_manual_edits = True
        course.has_unpublished_changes = False
        course.full_clean()
        course.save()

        question_data = {
            "学习任务卡1：识读零件图标题栏、尺寸标注与技术要求": {
                "question_type": "single",
                "stem": "零件图标题栏中通常不包含以下哪项内容？",
                "options": ["A. 零件名称", "B. 材料", "C. 图样比例", "D. 机床报警代码"],
                "correct_answer": ["D"],
                "analysis": "机床报警代码属于设备运行信息，不属于零件图标题栏内容。",
                "difficulty": "easy",
            },
            "学习任务卡2：开展零件结构工艺性分析": {
                "question_type": "judgment",
                "stem": "零件结构工艺性分析应同时考虑加工可达性、装夹方式和检测条件。",
                "options": [],
                "correct_answer": ["正确"],
                "analysis": "三者都会影响加工方案的可实施性。",
                "difficulty": "medium",
            },
            "学习任务卡1：确认毛坯材料与余量": {
                "question_type": "single",
                "stem": "确定毛坯加工余量时，首先应综合考虑什么？",
                "options": ["A. 材料与加工精度", "B. 操作者姓名", "C. 车间颜色", "D. 文件名称"],
                "correct_answer": ["A"],
                "analysis": "材料特性、毛坯状态与加工精度是确定余量的主要依据。",
                "difficulty": "easy",
            },
            "学习任务卡2：划分工序并制定加工路线": {
                "question_type": "single",
                "stem": "一般机械加工路线通常遵循的基本原则是？",
                "options": ["A. 先精后粗", "B. 先粗后精", "C. 随机加工", "D. 只加工一次"],
                "correct_answer": ["B"],
                "analysis": "通常先通过粗加工去除大部分余量，再进行精加工保证精度。",
                "difficulty": "easy",
            },
            "学习任务卡3：选择刀具并制定切削参数": {
                "question_type": "multiple",
                "stem": "制定数控加工切削参数时，应重点考虑哪些因素？",
                "options": ["A. 工件材料", "B. 刀具材料", "C. 加工精度", "D. 机床性能"],
                "correct_answer": ["A", "B", "C", "D"],
                "analysis": "切削参数应综合工件、刀具、质量要求和设备能力确定。",
                "difficulty": "medium",
            },
            "学习任务卡1：选择适配的夹具与定位方式": {
                "question_type": "single",
                "stem": "选择工件定位基准时，应优先保证什么？",
                "options": ["A. 定位稳定并减少误差", "B. 外观颜色统一", "C. 刀具数量最多", "D. 程序行数最少"],
                "correct_answer": ["A"],
                "analysis": "定位方案首先要保证稳定可靠，并尽量减小基准不重合误差。",
                "difficulty": "medium",
            },
            "学习任务卡2：完成工件装夹、找正与夹紧检查": {
                "question_type": "judgment",
                "stem": "工件装夹后，应确认夹紧可靠且不会因夹紧力过大造成工件变形。",
                "options": [],
                "correct_answer": ["正确"],
                "analysis": "夹紧不足会造成松动，夹紧过度也可能引起变形和加工误差。",
                "difficulty": "medium",
            },
        }
        for node_name, defaults in question_data.items():
            node = CourseTreeNode.objects.filter(
                tree=course,
                node_type="knowledge",
                name=node_name,
            ).first()
            if node is None:
                raise CommandError(f"课程树缺少演示任务卡：{node_name}")
            question, _ = CourseQuestion.objects.update_or_create(
                node=node,
                stem=defaults["stem"],
                defaults={**defaults, "created_by": course_owner},
            )
            question.full_clean()
            question.save()

        cnc_class = Class.objects.filter(name="数控2201班").first()
        if cnc_class is None:
            raise CommandError("未找到“数控2201班”")
        student, _ = Student.objects.update_or_create(
            student_id="DEMO-NC-001",
            defaults={
                "name": "张同学",
                "major": "数控技术",
                "grade": "2022级",
                "class_group": cnc_class,
                "phone": "",
                "user": student_user,
            },
        )
        Student.objects.filter(user=student_user).exclude(pk=student.pk).update(user=None)

        arrangement, _ = TeachingArrangement.objects.get_or_create(
            teacher=teacher,
            course_tree=course,
            semester="2026-2027-1",
        )
        arrangement.classes.add(cnc_class)

        semester_plan, _ = LearningPlan.objects.update_or_create(
            student=student,
            course_tree=course,
            plan_type=LearningPlan.PlanType.SEMESTER,
            defaults={
                "name": "数控加工工艺与编程",
                "category": "专业核心",
                "status": LearningPlan.Status.DOING,
                "progress": 46,
                "learned_hours": 29,
                "total_hours": 64,
                "deadline": date(2027, 1, 10),
                "teacher": "李思雨",
            },
        )
        LearningPlan.objects.update_or_create(
            student=student,
            name="数控加工安全操作强化训练",
            plan_type=LearningPlan.PlanType.AI,
            defaults={
                "category": "AI推荐",
                "status": LearningPlan.Status.DOING,
                "progress": 60,
                "learned_hours": 6,
                "total_hours": 10,
                "deadline": date(2026, 11, 30),
                "teacher": "李思雨",
            },
        )
        LearningPlan.objects.update_or_create(
            student=student,
            name="数控编程与仿真专项练习",
            plan_type=LearningPlan.PlanType.SELF,
            defaults={
                "category": "自主学习",
                "status": LearningPlan.Status.TODO,
                "progress": 0,
                "learned_hours": 0,
                "total_hours": 12,
                "deadline": date(2026, 12, 20),
                "teacher": "",
            },
        )

        records = [
            ("建立数控能力学习档案", "根据数控操作工正式能力树建立个人学习目标。", "入学"),
            ("完成零件图纸阅读任务", "完成零件图标题栏、尺寸标注及技术要求识读训练，任务评价良好。", "里程碑"),
            ("加工工艺方案阶段测评", "完成毛坯选择、工序划分和刀具参数测评，阶段成绩 86 分。", "测评"),
            ("夹具装夹安全规范达标", "完成工件定位、找正和夹紧检查训练，安全操作项目达标。", "成就"),
        ]
        for title, description, tag in records:
            LearningRecord.objects.update_or_create(
                student=student,
                title=title,
                defaults={"description": description, "tag": tag},
            )

        self.stdout.write(self.style.SUCCESS(
            "比赛演示数据准备完成："
            f"数控招聘原始 {len(results)} 条、去重后 {JobListing.objects.filter(job=job).count()} 条；"
            f"课程任务 {course.nodes.filter(node_type='chapter').count()} 个、"
            f"任务卡 {course.nodes.filter(node_type='knowledge').count()} 张、"
            f"试题 {CourseQuestion.objects.filter(node__tree=course).count()} 道；"
            f"学生计划 {LearningPlan.objects.filter(student=student).count()} 项、"
            f"学习记录 {LearningRecord.objects.filter(student=student).count()} 条。"
        ))
