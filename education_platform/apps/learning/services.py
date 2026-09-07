"""测评抽题与判分 + AI 学习计划推荐。

题库题型：single/multiple/judgment/short。自动判分只支持前三种（简答留空/主观）。
题目选项以 "A. 内容" 存储，correct_answer 存答案标签（如 ["A"] / ["A","B"] / ["正确"]）。
"""
import random
import re

from apps.curriculum.models import CourseTree, CourseTreeNode
from apps.teaching.models import CourseQuestion

from .models import AssessmentAnswer, AssessmentRun, LearningPlan, LearningProgress, PlanCourse, PlanPoint

AUTO_TYPES = {"single", "multiple", "judgment"}
DEFAULT_COUNTS = {"point": None, "chapter": 5, "course": 8}  # None = 全部


def tree_all_point_ids(course_tree):
    """一棵课程树的所有知识点 id（按 sort 排序）。"""
    return list(CourseTreeNode.objects.filter(
        tree=course_tree, node_type="knowledge",
    ).order_by("sort_order", "id").values_list("id", flat=True))


def plan_knowledge_points(plan):
    """某计划选中的所有知识点（PlanPoint.node，跨课程）。"""
    return list(CourseTreeNode.objects.filter(
        plan_points__plan_course__plan=plan, node_type="knowledge",
    ).distinct())


def plan_point_ids(plan):
    return [n.id for n in plan_knowledge_points(plan)]


def add_course_to_plan(plan, course_tree, node_ids=None):
    """把课程加入计划（整课或仅指定知识点）。返回 PlanCourse + 本次新增点数。"""
    plan_course, created = PlanCourse.objects.get_or_create(
        plan=plan, course_tree=course_tree,
        defaults={"sort_order": plan.courses.count()},
    )
    target_ids = node_ids if node_ids is not None else tree_all_point_ids(course_tree)
    existing = set(plan_course.points.values_list("node_id", flat=True))
    added = 0
    sort = plan_course.points.count()
    for nid in target_ids:
        if nid in existing:
            continue
        PlanPoint.objects.create(plan_course=plan_course, node_id=nid, sort_order=sort)
        added += 1
        sort += 1
    return plan_course, added


def plan_live_stats(student, plan):
    """计划实时统计：总学时=所含课程学时和；进度=已完成知识点数/总数。"""
    total_hours = sum(
        pc.course_tree.total_hours
        for pc in plan.courses.select_related("course_tree")
        if pc.course_tree_id
    )
    point_ids = list(PlanPoint.objects.filter(plan_course__plan=plan).values_list("node_id", flat=True))
    total_points = len(point_ids)
    done = LearningProgress.objects.filter(student=student, node_id__in=point_ids).count() if point_ids else 0
    progress = round(done / total_points * 100) if total_points else 0
    learned_hours = round(total_hours * progress / 100)
    return {
        "total_hours": total_hours,
        "total_points": total_points,
        "done_points": done,
        "progress": progress,
        "learned_hours": learned_hours,
    }


def _course_structure(tree, node_ids=None):
    """单课结构（章 → 点）。node_ids 非空时仅保留指定知识点。"""
    nodes = list(CourseTreeNode.objects.filter(tree=tree).order_by("sort_order", "id"))
    chapters = []
    for ch in [n for n in nodes if n.node_type == "chapter"]:
        pts = [n for n in nodes if n.node_type == "knowledge" and n.parent_id == ch.id]
        if node_ids is not None:
            pts = [p for p in pts if p.id in node_ids]
        if not pts:
            continue
        chapters.append({
            "chapter_id": ch.id, "chapter_name": ch.name,
            "points": [{"id": p.id, "name": p.name, "desc": p.task_description or ""} for p in pts],
        })
    return {
        "course_id": tree.id, "course_name": tree.name,
        "course_type": tree.get_course_type_display(), "hours": tree.total_hours,
        "chapters": chapters,
    }


def list_course_library():
    """课程库：所有已发布课程 → 章 → 知识点（供新增计划/计划调整勾选用）。"""
    return [
        _course_structure(t)
        for t in CourseTree.objects.filter(is_published=True).order_by("name", "id")
    ]


def create_plan_from_courses(student, name, selections, plan_type="self", category="自主学习"):
    """批量建一条学习计划：selections=[{course_id, node_ids?}]（node_ids 省略=整课全点）。

    任一课程不可用 / 全部无有效知识点 → 整体回滚（不留空计划）。
    """
    from django.db import transaction

    if not selections:
        raise ValueError("请至少选择一门课程")
    if plan_type not in LearningPlan.PlanType.values:
        plan_type = LearningPlan.PlanType.SELF
    default_name = (
        f"{student.name}的AI推荐计划" if plan_type == LearningPlan.PlanType.AI
        else f"{student.name}的自主学习计划"
    )
    with transaction.atomic():
        plan = LearningPlan.objects.create(
            student=student,
            name=name or default_name,
            category=category or "自主学习",
            plan_type=plan_type,
        )
        total_points = 0
        for sel in selections:
            tree = CourseTree.objects.filter(pk=sel["course_id"], is_published=True).first()
            if tree is None:
                raise ValueError("所选课程不可用")
            node_ids = sel.get("node_ids") if sel.get("node_ids") else None
            # 未指定 node_ids = 整课；指定了但不属于该课则忽略该课
            if node_ids is not None:
                valid = CourseTreeNode.objects.filter(
                    tree=tree, node_type="knowledge", id__in=node_ids,
                ).values_list("id", flat=True)
                node_ids = list(valid)
                if not node_ids:
                    continue
            _, added = add_course_to_plan(plan, tree, node_ids=node_ids)
            total_points += added
        # 全部无有效知识点 → 抛出回滚这条空计划
        if plan.courses.count() == 0:
            raise ValueError("请至少选择一个知识点")
    return plan, total_points


def analyze_student_weakness(student, plan):
    """按学生在某计划所含知识点上的正确率给薄弱项。真 AI 优先，无 key 按规则(<70% 视为薄弱)。"""
    from ai import services as ai_services
    from django.db.models import Count, Q

    point_ids = plan_point_ids(plan)
    if not point_ids:
        return {"source": "none", "summary": "该计划暂无知识点", "weak_points": []}
    # 聚合：计划内各知识点的作答对错
    rows = (AssessmentAnswer.objects
            .filter(run__student=student, node_id__in=point_ids)
            .values("node__name")
            .annotate(total=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
            .order_by("node__name"))
    stats = [{"node_name": r["node__name"], "total": r["total"], "correct": r["correct"]} for r in rows if r["total"]]
    if not stats:
        return {"source": "none", "summary": "暂无该计划的测评记录", "weak_points": []}

    if ai_services.ai_available():
        try:
            result = ai_services.analyze_learning_weakness(stats)
            result.setdefault("source", "ai")
            return result
        except Exception:
            pass
    weak = []
    for s in stats:
        mastery = round(s["correct"] / s["total"] * 100) if s["total"] else 100
        if mastery < 70:
            weak.append({"node_name": s["node_name"], "mastery": mastery,
                         "suggestion": "回看该知识点内容并重新完成随堂练习"})
    weak.sort(key=lambda x: x["mastery"])
    return {"source": "rule", "summary": f"共 {len(stats)} 个知识点有测评记录", "weak_points": weak}


def _questions_in_scope(scope, plan=None, node_id=None):
    """返回某测评范围内可自动判分的题目。

    范围以「该计划选中的知识点」为界：随堂=该点（须在计划内）；章节=该章在计划内的点；课程=计划全部点。
    """
    plan_points = plan_point_ids(plan) if plan is not None else None
    qs = CourseQuestion.objects.filter(question_type__in=AUTO_TYPES)
    if scope == AssessmentRun.Scope.POINT:
        qs = qs.filter(node_id=node_id)
    elif scope == AssessmentRun.Scope.CHAPTER:
        # 章节测验：该章下、且属于计划选中的知识点
        chapter = CourseTreeNode.objects.filter(pk=node_id, node_type="chapter").first()
        if chapter is None:
            return CourseQuestion.objects.none()
        ch_point_ids = list(CourseTreeNode.objects.filter(
            parent_id=chapter.id, node_type="knowledge",
        ).values_list("id", flat=True))
        if plan_points is not None:
            ch_point_ids = [pid for pid in ch_point_ids if pid in plan_points]
        qs = qs.filter(node_id__in=ch_point_ids)
    else:  # course
        if plan_points:
            qs = qs.filter(node_id__in=plan_points)
        else:
            return CourseQuestion.objects.none()
    return qs


def pick_questions(scope, plan=None, node_id=None, student=None):
    """按范围抽取题目列表（含正确答案标签，供提交端判分）。"""
    pool = list(_questions_in_scope(scope, plan=plan, node_id=node_id))
    limit = DEFAULT_COUNTS.get(scope)
    if limit and len(pool) > limit:
        pool = random.sample(pool, limit)
    return pool


def _norm_label(label):
    """把答案标签归一化为比对键。"""
    s = str(label).strip()
    low = s.casefold()
    if low in {"true", "正确", "对"}:
        return "对"
    if low in {"false", "错误", "错"}:
        return "错"
    return s.upper()


def _is_correct(question, chosen):
    """判分：单选/判断比对单答案，多选比对集合。简答不计分（True 但当 subjective）。"""
    expected = {_norm_label(x) for x in question.correct_answer}
    picked = {_norm_label(x) for x in (chosen or [])}
    if question.question_type == "multiple":
        return bool(expected) and picked == expected
    # single / judgment / short
    return bool(expected) and picked == expected


def submit_run(*, student, plan, scope, node, title, answers, questions):
    """根据提交的作答创建测评记录与明细，返回 (run, per_question_result)。"""
    correct = wrong = 0
    results = []
    by_id = {q.id: q for q in questions}
    # 只保留属于本测评展示题目的作答
    answered = [a for a in answers if a.get("question_id") in by_id]
    run = AssessmentRun.objects.create(
        student=student, plan=plan, scope=scope, node=node, title=title,
        question_ids=list(by_id.keys()),
        total=len(by_id),
    )
    for item in answered:
        question = by_id[item["question_id"]]
        chosen = item.get("chosen") or []
        ok = _is_correct(question, chosen)
        if ok:
            correct += 1
        else:
            wrong += 1
        AssessmentAnswer.objects.create(
            run=run, question=question,
            node=question.node if question.node_id else None,
            chosen=chosen, is_correct=ok,
        )
        results.append({"question_id": question.id, "is_correct": ok})
    run.score = correct
    run.correct_count = correct
    run.wrong_count = wrong
    run.save(update_fields=["score", "correct_count", "wrong_count"])
    return run, results


def chapter_point_ids(chapter_id):
    return list(CourseTreeNode.objects.filter(
        parent_id=chapter_id, node_type="knowledge",
    ).values_list("id", flat=True))


# ===== 新增计划向导（按岗位 / 按课程 / AI 目标推荐 / 摸底）=====

def list_job_options():
    """岗位列表（按岗位创建用）：只返回有已发布课程关联的岗位。

    课程↔岗位通过 CourseTree.source_ability（能力节点）→ CapabilityNode.job 建立。
    """
    from apps.industry.models import Job

    jobs = []
    for job in Job.objects.filter(is_enabled=True, chain__is_enabled=True).order_by("name", "id"):
        trees = list(CourseTree.objects.filter(
            source_ability__job=job, source_ability__node_type="ability", is_published=True,
        ).order_by("name", "id"))
        if not trees:
            continue
        course_ids = [t.id for t in trees]
        point_count = CourseTreeNode.objects.filter(
            tree_id__in=course_ids, node_type="knowledge",
        ).count()
        jobs.append({
            "job_id": job.id,
            "job_name": job.name,
            "industry": job.chain.name if job.chain_id else "",
            "course_ids": course_ids,
            "course_count": len(course_ids),
            "point_count": point_count,
        })
    return jobs


def chat_reply(message, history):
    """AI 目标推荐的多轮对话回话（规则降级，与原型关键词逻辑一致）。"""
    text = (message or "").strip().lower()
    turn = sum(1 for m in history if m.get("role") == "user")
    if re.search(r"多久|周期|几个月|周|天", text):
        return "了解时间安排了。一般来说 8–12 周可以完成一门核心课加配套实训。你更倾向「快速上岗」还是「扎实打基础」？"
    if re.search(r"基础|零基础|小白|不会|入门", text):
        return "收到，你偏零基础入门。建议先从概念与安全规范开始，再进入示教/编程实操。你最想先接触机器人、PLC，还是数控？"
    if re.search(r"机器人|示教|联调|装调", text):
        return "机器人方向很清晰。后续可覆盖示教编程、坐标系与产线联调。你是否还需要补 PLC 通信或安全联锁相关内容？"
    if re.search(r"plc|通信", text):
        return "PLC/通信方向已记录。可以围绕梯形图、工业通信与联调排错展开。你有没有特定品牌或现场场景要求？"
    if re.search(r"数控|加工", text):
        return "数控加工方向已记下。后续可匹配编程、对刀与伺服参数等内容。你更侧重编程，还是机床操作？"
    if re.search(r"视觉|检测|伺服", text):
        return "可以，工业视觉/伺服也是常见强化方向。你希望它作为主修，还是作为机器人/PLC 计划的补充模块？"
    if turn <= 1:
        return "好的，我先记下你的目标。你可以再补充：当前基础、期望时长，以及更偏向理论还是实操。"
    if turn == 2:
        return "信息更完整了。若还有岗位要求或必须掌握的知识点，也可以继续说；准备好后点击「生成计划」。"
    return "已更新你的需求。你可以继续补充细节，或直接点击「生成计划」让我据此匹配课程。"


def recommend_from_chat(history):
    """根据聊天历史匹配课程（真 AI 优先，无 key 按关键词规则）。返回 {source, courses:[{course_id, course_name}]}。"""
    from ai import services as ai_services

    text = " ".join(m.get("text", "") for m in history if m.get("role") == "user").lower()
    catalog = list(CourseTree.objects.filter(is_published=True).order_by("name", "id"))
    if ai_services.ai_available():
        try:
            result = ai_services.match_courses_from_chat(text, catalog)
            result.setdefault("source", "ai")
            return result
        except Exception:
            pass
    # 规则降级：聊天关键词 → 课程名关键词打分，取 top 3
    kw_map = {
        "机器人": "机器人", "示教": "机器人", "联调": "集成", "装调": "集成",
        "plc": "PLC", "通信": "PLC",
        "数控": "数控", "加工": "数控",
        "伺服": "伺服",
        "视觉": "视觉", "检测": "视觉",
    }
    scored = []
    for t in catalog:
        score = 0
        for kw, hint in kw_map.items():
            if kw in text and hint in t.name:
                score += 1
        scored.append((score, t))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    picks = [t for s, t in scored if s > 0][:3] or catalog[:3]
    return {
        "source": "rule",
        "courses": [{"course_id": t.id, "course_name": t.name} for t in picks],
    }


def build_placement_test(course_ids):
    """摸底自测题：从所选课程知识点抽单选真题，每课≤2 题、总≤8。"""
    questions = []
    for cid in course_ids:
        node_ids = list(CourseTreeNode.objects.filter(
            tree_id=cid, node_type="knowledge",
        ).values_list("id", flat=True))
        if not node_ids:
            continue
        questions.extend(list(
            CourseQuestion.objects.filter(question_type="single", node_id__in=node_ids)
            .select_related("node").order_by("id")[:2]
        ))
    return [{
        "question_id": q.id,
        "stem": q.stem,
        "options": q.options or [],
        "course_id": q.node.tree_id,
        "node_id": q.node_id,
    } for q in questions[:8]]


def grade_placement_test(course_ids, answered):
    """判分摸底并返回精简+排序后的课程结构（薄弱课优先，掌握好的精简知识点）。"""
    qids = [a.get("question_id") for a in answered if a.get("question_id")]
    qs = list(CourseQuestion.objects.filter(id__in=qids).select_related("node"))
    by_id = {q.id: q for q in qs}
    correct = 0
    wrong_courses = set()
    wrong_nodes = set()
    for a in answered:
        q = by_id.get(a.get("question_id"))
        if q is None:
            continue
        idx = a.get("chosen_index")
        letter = chr(65 + int(idx)) if idx is not None else ""
        if _is_correct(q, [letter]):
            correct += 1
        else:
            wrong_courses.add(q.node.tree_id)
            wrong_nodes.add(q.node_id)
    total = len(qids)
    ratio = correct / total if total else 0

    order = {cid: i for i, cid in enumerate(course_ids)}
    trees = list(CourseTree.objects.filter(id__in=course_ids, is_published=True))
    trees.sort(key=lambda t: (0 if t.id in wrong_courses else 1, order.get(t.id, 99)))

    courses_out = []
    for t in trees:
        nodes = list(CourseTreeNode.objects.filter(tree=t).order_by("sort_order", "id"))
        chapters = [n for n in nodes if n.node_type == "chapter"]
        keep = None
        if ratio >= 0.75 and t.id not in wrong_courses:
            keep = set()
            for ch in chapters:
                pts = [n for n in nodes if n.node_type == "knowledge" and n.parent_id == ch.id]
                if pts:
                    keep.add(pts[0].id)
        elif wrong_nodes:
            keep = set()
            for ch in chapters:
                pts = [n for n in nodes if n.node_type == "knowledge" and n.parent_id == ch.id]
                if any(p.id in wrong_nodes for p in pts):
                    keep.update(p.id for p in pts)
                else:
                    keep.update(p.id for p in pts[:2])
        c = _course_structure(t, node_ids=keep)
        if c["chapters"]:
            courses_out.append(c)
    return {"source": "ai", "correct": correct, "total": total, "courses": courses_out}
