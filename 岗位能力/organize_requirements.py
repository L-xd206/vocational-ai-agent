"""
整理岗位要求 — 从爬取JSON中提取、去重、清洗，输出干净文本
=========================================================
用法:
  python organize_requirements.py                          # 自动找最新JSON
  python organize_requirements.py data/电工_爬取结果.json   # 指定文件

输出: output/{岗位名}_岗位要求.txt
"""
import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def clean_text(text: str) -> str:
    """清洗单条招聘要求"""
    # 去掉乱码字符
    text = text.replace("？", "").replace("．", "").replace("？", "")
    # 去掉多余的空白
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[-–—]{3,}", "", text)  # 去掉长分隔线
    text = text.strip()
    return text


def organize(filepath: str = None):
    # 找文件
    if filepath:
        fp = Path(filepath)
    else:
        files = sorted(DATA_DIR.glob("*_爬取结果.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        fp = files[0] if files else None

    if not fp or not fp.exists():
        print("未找到数据文件")
        return

    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)

    keyword = data.get("search_keyword", "岗位")
    results = data.get("results", [])

    # 提取 + 去重 + 清洗
    seen = set()
    clean_reqs = []
    total_empty = 0

    for r in results:
        req = r.get("requirements", "").strip()
        if not req or len(req) < 10:
            total_empty += 1
            continue
        key = req[:40]  # 用前40字去重
        if key in seen:
            continue
        seen.add(key)
        clean_reqs.append(clean_text(req))

    # 保存
    out_file = OUTPUT_DIR / f"{keyword}_岗位要求.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"# {keyword} 岗位要求汇总\n")
        f.write(f"# 数据来源: 中国公共招聘网\n")
        f.write(f"# 原始条数: {len(results)} | 去重后: {len(clean_reqs)} 条 | 空记录: {total_empty}\n\n")
        for i, req in enumerate(clean_reqs, 1):
            f.write(f"{req}\n\n")

    print(f"\n  原始: {len(results)} 条")
    print(f"  去重: {len(clean_reqs)} 条")
    print(f"  空记录: {total_empty} 条")
    print(f"  保存: {out_file}")

    # 打印前3条预览
    print(f"\n  预览 (前3条):")
    for i, req in enumerate(clean_reqs[:3], 1):
        print(f"  [{i}] {req[:120]}...")


if __name__ == "__main__":
    fp = sys.argv[1] if len(sys.argv) > 1 else None
    organize(fp)
