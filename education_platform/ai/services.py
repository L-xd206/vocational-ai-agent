"""供业务 app 调用的 AI 门面，避免视图直接依赖脚本文件。"""


def generate_jobs(chain_name: str) -> dict:
    from ai.jobs import gen_jobs
    return gen_jobs(chain_name)


def generate_capability_map(job_name: str, requirements: list[str]) -> dict:
    from ai.capability_generation import gen_ability
    return gen_ability(job_name, requirements)
