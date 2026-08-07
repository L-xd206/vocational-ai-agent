import re


INVALID_JOB_NAMES = {"a", "ch", "test", "null", "none", "未知", "无"}


def validate_job_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if not name:
        raise ValueError("请输入岗位名称")
    if len(name) > 100:
        raise ValueError("岗位名称不能超过100个字符")
    if name.casefold() in INVALID_JOB_NAMES:
        raise ValueError("岗位名称没有实际意义，请输入真实岗位名称")
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", name):
        raise ValueError("岗位名称不能只包含符号")
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", name))
    alpha_num_count = len(re.findall(r"[A-Za-z0-9]", name))
    if chinese_count < 2 and alpha_num_count < 4:
        raise ValueError("岗位名称过短，请输入完整名称")
    if len(set(name.casefold())) == 1:
        raise ValueError("岗位名称不能是重复字符")
    return name


def normalize_keywords(values) -> list[str]:
    if isinstance(values, str):
        values = re.split(r"[,，\n;；]+", values)
    if not isinstance(values, (list, tuple)):
        raise ValueError("搜索关键词必须是列表或以逗号分隔的文本")

    result = []
    seen = set()
    for value in values:
        keyword = re.sub(r"\s+", " ", str(value or "").strip())
        if not keyword or keyword.casefold() in seen:
            continue
        if len(keyword) < 2 or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", keyword):
            raise ValueError(f"搜索关键词“{keyword}”无效")
        seen.add(keyword.casefold())
        result.append(keyword)
    if len(result) < 3:
        raise ValueError("请至少填写3个不同的搜索关键词")
    return result
