"""预置教学课程/教学安排/学习内容测试数据（幂等，可重复执行）

用法：python manage.py seed_teaching
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.curriculum.api import create_course_tree
from apps.curriculum.models import CourseTreeNode
from apps.organizations.api import get_classes_by_college
from apps.organizations.models import Organization
from apps.teaching.models import CourseQuestion, TeachingArrangement

User = get_user_model()

# 6 门课（参照原型），每门带章节→知识点+学习内容，供 AI 推荐/计划调整/学习界面用
COURSES = [
    {
        "name": "工业机器人技术基础", "hours": 64, "credits": 4, "course_type": "integrated",
        "chapters": [
            ("机器人概述与发展", [
                ("机器人定义与分类", "掌握工业机器人的基本定义和常见分类方式", "机器人装配车间"),
                ("机器人发展历程", "了解国内外工业机器人发展历程及趋势", "工业机器人展厅"),
            ]),
            ("机器人运动学基础", [
                ("坐标系变换", "掌握齐次坐标变换与 DH 参数法", "机器人标定工位"),
                ("正向运动学", "建立机器人运动学方程并求解末端位姿", "仿真实验室"),
            ]),
            ("机器人轨迹规划", [
                ("运动轨迹校准", "掌握示教轨迹的校准与优化方法", "示教编程工位"),
            ]),
        ],
    },
    {
        "name": "PLC编程与应用", "hours": 56, "credits": 3.5, "course_type": "integrated",
        "chapters": [
            ("PLC基础与硬件结构", [
                ("PLC工作原理", "掌握 PLC 循环扫描工作原理", "PLC 实训台"),
                ("硬件模块", "了解 CPU、I/O、通信模块功能", "电气控制柜"),
            ]),
            ("梯形图编程", [
                ("梯形图基本指令", "掌握梯形图基本指令与编程方法", "编程软件工位"),
                ("定时器与计数器", "学习定时器和计数器的使用方法", "PLC 实训台"),
            ]),
        ],
    },
    {
        "name": "数控加工技术", "hours": 48, "credits": 3, "course_type": "practice",
        "chapters": [
            ("数控编程基础", [
                ("G代码编程", "掌握常用 G 代码指令及编程方法", "数控加工中心"),
                ("坐标系建立", "学习工件坐标系与机床坐标系建立", "数控机床"),
            ]),
            ("数控加工实训", [
                ("对刀操作", "掌握数控机床对刀方法与步骤", "数控车床"),
                ("刀具补偿", "学习刀具半径补偿与长度补偿", "数控加工中心"),
            ]),
        ],
    },
    {
        "name": "伺服系统应用", "hours": 40, "credits": 2.5, "course_type": "theory",
        "chapters": [
            ("伺服系统原理", [
                ("伺服电机原理", "掌握交流伺服电机工作原理", "伺服驱动实训台"),
                ("伺服驱动器", "了解伺服驱动器结构与控制方式", "电气实训室"),
            ]),
            ("伺服参数配置", [
                ("三环参数整定", "位置环/速度环/电流环参数整定", "伺服调试工位"),
                ("报警诊断", "常见伺服报警分析与处理", "伺服实训台"),
            ]),
        ],
    },
    {
        "name": "智能制造系统集成实训", "hours": 48, "credits": 3, "course_type": "practice",
        "chapters": [
            ("系统集成联调", [
                ("信号联锁测试", "完成安全联锁与 I/O 信号验证", "智能产线"),
                ("通信协议验证", "现场总线通信联调与排错", "智能产线"),
            ]),
            ("装调与排故", [
                ("产线装调流程", "按工艺完成工位装调与验收", "装配工位"),
            ]),
        ],
    },
    {
        "name": "工业视觉检测技术", "hours": 32, "credits": 2, "course_type": "integrated",
        "chapters": [
            ("视觉检测基础", [
                ("相机标定", "完成工业相机内外参标定", "视觉检测台"),
                ("缺陷检测", "构建基础缺陷检测流程", "视觉检测台"),
            ]),
        ],
    },
]

STEPS = ["熟悉设备与工具", "按标准流程完成操作", "记录并复核结果"]
SAFETY = ["穿戴劳保用品", "确认急停装置可用"]


class Command(BaseCommand):
    help = "预置教学课程、学习内容与教学安排测试数据（幂等）"

    def handle(self, *args, **options):
        college = Organization.objects.filter(name="智能制造学院", org_type="学院").first()
        course_owner = User.objects.filter(username="course_owner").first()
        teacher_user = User.objects.filter(username="teacher").first()
        if not college or not course_owner or not teacher_user:
            self.stdout.write("⚠ 缺学院/课程负责人/教师账号，跳过教学 seed")
            return

        trees = {}
        first_point = None
        for course in COURSES:
            tree = create_course_tree(
                organization=college, name=course["name"], owner=course_owner,
                is_published=True, total_hours=course["hours"],
                credits=course["credits"], course_type=course["course_type"],
            )
            trees[course["name"]] = tree
            for ch_name, points in course["chapters"]:
                chapter, _ = CourseTreeNode.objects.get_or_create(
                    tree=tree, node_type="chapter", name=ch_name, defaults={"parent": None},
                )
                for idx, (pt_name, desc, scenario) in enumerate(points):
                    point, _ = CourseTreeNode.objects.update_or_create(
                        tree=tree, parent=chapter, node_type="knowledge", name=pt_name,
                        defaults={
                            "task_description": desc,
                            "work_scenario": scenario,
                            "operation_steps": STEPS,
                            "safety_points": SAFETY,
                            "resource_links": [f"《{course['name']}》教材第 {idx + 1} 章"],
                            "sort_order": idx,
                        },
                    )
                    if first_point is None:
                        first_point = point

        # 试题挂在第一门课的第一个知识点（供试题库检索）
        if first_point is not None:
            CourseQuestion.objects.get_or_create(
                node=first_point, question_type="single", stem="工业机器人的基本组成部分不包括以下哪项？",
                defaults={"options": ["A. 机械臂", "B. 驱动系统", "C. 操作系统", "D. 控制系统"], "correct_answer": ["C"], "difficulty": "easy"},
            )
            CourseQuestion.objects.get_or_create(
                node=first_point, question_type="multiple", stem="下列属于工业机器人分类方式的有？",
                defaults={"options": ["A. 按坐标型式", "B. 按驱动方式", "C. 按控制方式", "D. 按自由度"], "correct_answer": ["A", "B", "C", "D"], "difficulty": "medium"},
            )

        # 教学安排：teacher 排「工业机器人技术基础」
        tree = trees["工业机器人技术基础"]
        classes = list(get_classes_by_college(college.id))
        if classes:
            arr, created = TeachingArrangement.objects.get_or_create(
                teacher=teacher_user, course_tree=tree, semester="2025-2026-1",
            )
            arr.classes.set(classes[:2])

        # 为所有知识点生成测评题（幂等：同一知识点+题干不重复）
        self._seed_quiz_for_nodes()
        self.stdout.write(self.style.SUCCESS(
            f"seed_teaching 完成：{CourseTreeNode.objects.count()} 个课程节点，"
            f"{TeachingArrangement.objects.count()} 条教学安排，{CourseQuestion.objects.count()} 道试题"
        ))

    def _seed_quiz_for_nodes(self):
        """每个知识点 3 道自动判分题（单选/判断/多选），供测评抽题。"""
        points = CourseTreeNode.objects.filter(node_type="knowledge")
        template_sets = [
            ("single", "关于「{name}」的核心概念，以下理解正确的是？",
             ["A. 该知识点与岗位能力无关", "B. 需理解其基本定义、流程与适用场景", "C. 只需记住名称即可", "D. 不需要任何基础即可掌握"], ["B"]),
            ("judgment", "「{name}」属于本课程需要掌握的学习内容。",
             [], ["正确"]),
            ("multiple", "学习「{name}」时，以下做法合理的有？",
             ["A. 结合图文/视频理解原理", "B. 对照安全规范操作", "C. 跳过练习直接下一节", "D. 记录易错点并复盘"], ["A", "B", "D"]),
        ]
        for point in points:
            for qtype, stem_tpl, options, answer in template_sets:
                stem = stem_tpl.format(name=point.name)
                _, created = CourseQuestion.objects.get_or_create(
                    node=point, question_type=qtype, stem=stem,
                    defaults={
                        "options": options,
                        "correct_answer": answer,
                        "analysis": "本题考查「{name}」的学习要点。".format(name=point.name),
                        "difficulty": "easy",
                    },
                )
