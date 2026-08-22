"""供业务 app 调用的 AI 门面，避免视图直接依赖脚本文件。"""


def generate_jobs(chain_name: str) -> dict:
    from ai.jobs import gen_jobs
    return gen_jobs(chain_name)


def generate_capability_map(
    job_name: str,
    requirements: list[str],
    official_tree: list | None = None,
) -> dict:
    from ai.capability_generation import gen_ability
    return gen_ability(job_name, requirements, official_tree=official_tree)


def generate_course_task_tree(ability_snapshot: dict, textbook_catalog: dict) -> dict:
    """把正式岗位能力和教材目录交给 AI，返回学习任务树。"""
    from ai.course_generation import generate_learning_task_tree
    return generate_learning_task_tree(ability_snapshot, textbook_catalog)


def select_course_textbook(ability_snapshot: dict, textbook_index: dict) -> dict:
    """从学院教材知识库中自动选择最匹配教材。"""
    from ai.course_generation import select_textbook_for_ability
    return select_textbook_for_ability(ability_snapshot, textbook_index)
