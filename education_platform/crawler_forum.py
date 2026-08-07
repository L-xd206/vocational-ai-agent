"""
论坛帖子爬虫 — UG爱好者论坛 (ugsnx.com)
========================================
从CNC/数控专业论坛按顺序爬取一线工人真实技术讨论。
自动过滤置顶帖，按页面原始顺序全量爬取。

用法:
  python crawler_forum.py --all               # 全部版块，最近30天
  python crawler_forum.py --all 3 90          # 全部版块，3页，90天内
  python crawler_forum.py 刀路                # 含"刀路"的帖子
  python crawler_forum.py --forum 45 --all    # 仅"数控加工"版块全部帖
  python crawler_forum.py --forum 45 刀路     # 数控加工版块含"刀路"的
  python crawler_forum.py --list              # 列出所有可用版块
"""
import json
import re
import sys
import time
from pathlib import Path
from html import unescape
import requests

OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# CNC/数控相关的版块
FORUMS = {
    "45":  "数控加工",
    "120": "NX数控编程",
    "122": "加工中心",
    "118": "UG编程",
    "123": "NX后处理",
    "124": "NX机床仿真",
}

BASE = "https://www.ugsnx.com"


def bypass_captcha(session: requests.Session) -> bool:
    """绕过数学验证码"""
    try:
        r = session.get(f"{BASE}/forum-45-1.html", timeout=10)
        m = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)\s*=\s*\?", r.text)
        if not m:
            return "验证" not in r.text
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == "+" else (a - b if op == "-" else (a * b if op == "*" else a // b))
        session.post(f"{BASE}/forum.php",
                     data={"answer": str(ans), "secqsubmit": "Submit"},
                     headers={"Referer": f"{BASE}/forum-45-1.html"}, timeout=10)
        return True
    except Exception:
        return False


def _parse_thread_list(html: str, keyword: str = "") -> list[dict]:
    """
    从版块页面解析普通帖子列表。
    关键：只解析 <tbody id="normalthread_XXX">，这些是普通帖子。
    置顶帖用 <tbody id="stickthread_XXX">，我们跳过。
    """
    posts = []
    seen = set()

    for m in re.finditer(
        r'<tbody[^>]*id="normalthread_(\d+)"[^>]*>(.*?)</tbody>',
        html, re.DOTALL
    ):
        tid = m.group(1)
        body = m.group(2)

        # 标题链接 — 必须匹配 class="s xst" 才是真正的标题
        t_m = re.search(
            r'class="s\s+xst"[^>]*href="([^"]*thread-\d+-1-1\.html)"[^>]*>(.*?)</a>',
            body, re.DOTALL
        )
        if not t_m:
            t_m = re.search(
                r'href="([^"]*thread-\d+-1-1\.html)"[^>]*class="s\s+xst"[^>]*>(.*?)</a>',
                body, re.DOTALL
            )
        if not t_m:
            continue
        url = t_m.group(1)
        if not url.startswith("http"):
            url = BASE + "/" + url
        title = unescape(re.sub(r"<[^>]+>", "", t_m.group(2))).strip()

        if not title or url in seen:
            continue
        seen.add(url)

        # 关键词过滤
        if keyword and keyword not in title:
            continue

        # 日期 — 取 td.by em 里的发帖时间，不是最后回复时间
        # td.by 结构: <cite>作者</cite><em><span title="日期">相对时间</span></em>
        # 近期帖子用 <span title="2026-7-24">4小时前</span>
        # 老帖直接显示纯文本 "2024-3-23"（不在 span 里）
        post_date = ""
        by_td = re.search(r'<td[^>]*class="by"[^>]*>(.*?)</td>', body, re.DOTALL)
        if by_td:
            by_html = by_td.group(1)
            # 优先取 span title
            span_m = re.search(r'<span[^>]*title="(\d{4}-\d{1,2}-\d{1,2})"', by_html)
            if span_m:
                post_date = span_m.group(1)
            else:
                # 取纯文本日期 如 2024-3-23
                text_m = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', by_html)
                if text_m:
                    post_date = text_m.group(1)

        # 最后回复时间（备用）
        lp_m = re.search(r'lastpost[^>]*>.*?<span[^>]*title="(\d{4}-\d{1,2}-\d{1,2}[^"]*)"', body, re.DOTALL)
        last_reply = lp_m.group(1) if lp_m else ""

        # 作者
        a_m = re.search(r'<a\s+href="space-uid-\d+[^"]*"[^>]*>([^<]+)</a>', body)
        author = a_m.group(1).strip() if a_m else ""

        # 回复数 & 查看数 — <td class="num">
        nums = re.findall(r'<td[^>]*class="num"[^>]*>.*?<a[^>]*>(\d+)</a>', body, re.DOTALL)
        replies = int(nums[0]) if nums else 0
        views = int(nums[1]) if len(nums) > 1 else 0

        # 帖子分类 — [求助] [分享] 等
        cat_m = re.search(r'<em>\s*\[<a[^>]*>([^<]+)</a>\]\s*</em>', body)
        category = cat_m.group(1).strip() if cat_m else "讨论"

        posts.append({
            "tid": tid,
            "title": title,
            "url": url,
            "date": post_date,           # 发帖时间
            "last_reply": last_reply,     # 最后回复时间
            "author": author,
            "replies": replies,
            "views": views,
            "category": category,
            "source": "UG爱好者论坛",
        })

    return posts


def _fetch_post_content(session: requests.Session, url: str) -> dict | None:
    """获取帖子正文 + 回帖"""
    try:
        r = session.get(url, timeout=10)
        html = r.text
    except Exception:
        return None

    # 帖子正文 — <div class="pct">
    content = ""
    for m in re.finditer(r'<div[^>]*class="pct"[^>]*>(.*?)</div>', html, re.DOTALL):
        text = unescape(re.sub(r"<[^>]+>", "\n", m.group(1)))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        # 跳过图片/附件为主的
        if text.count(".png") + text.count(".jpg") + text.count(".rar") > len(text.split()) / 2:
            continue
        if len(text) > len(content):
            content = text

    # 回帖
    replies = []
    for m in re.finditer(r'<div[^>]*class="pct"[^>]*>(.*?)</div>', html, re.DOTALL):
        text = unescape(re.sub(r"<[^>]+>", " ", m.group(1)))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 40 and text[:40] != content[:40]:
            replies.append(text[:600])

    return {
        "content": content[:3000],
        "reply_texts": replies[:4],
        "replies": len(replies),
    }


def crawl(keyword: str, max_pages: int = 3, days_limit: int = 365,
          forum_id: str = None) -> list[dict]:
    """
    Args:
        keyword:    关键词，空字符串=不筛选
        max_pages:  爬几页
        days_limit: 只取最近多少天
        forum_id:   指定版块ID，None=全部版块
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    })

    print("  绕过验证码...", end=" ", flush=True)
    if not bypass_captcha(session):
        print("失败"); return []
    print("OK")

    all_posts = []
    forums_to_crawl = {forum_id: FORUMS[forum_id]} if forum_id else FORUMS

    for fid, fname in forums_to_crawl.items():
        for page in range(1, max_pages + 1):
            print(f"  [{fname}] 第{page}页...", end=" ", flush=True)
            try:
                r = session.get(f"{BASE}/forum-{fid}-{page}.html", timeout=10)
                threads = _parse_thread_list(r.text, keyword)
            except Exception as e:
                print(f"失败: {e}"); break

            if not threads:
                print("无帖"); break

            # 按发帖日期过滤（不是最后回复日期）
            recent = []
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=days_limit)
            for t in threads:
                d_str = t.get("date", "")
                try:
                    if d_str:
                        d = datetime.strptime(d_str, "%Y-%m-%d")
                    else:
                        d = datetime.now()  # 无日期视为新帖
                    if d >= cutoff:
                        recent.append(t)
                except ValueError:
                    recent.append(t)

            # 保持页面原始顺序（按最后回复时间降序），不排序
            # 逐条获取详情 — 全部爬，不限制数量
            for t in recent:
                detail = _fetch_post_content(session, t["url"])
                if detail:
                    t.update(detail)
                all_posts.append(t)
                time.sleep(0.3)

            print(f"{len(threads)}帖, {len(recent)}新 (累计{len(all_posts)})")

            if len(threads) < 15:
                break

            time.sleep(0.6)

    return all_posts


def save(posts: list[dict], keyword: str):
    if not posts:
        return
    filepath = OUTPUT_DIR / f"{keyword}_论坛帖子.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "keyword": keyword,
            "total": len(posts),
            "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "posts": posts,
        }, f, ensure_ascii=False, indent=2)

    # 统计
    with_content = [p for p in posts if len(p.get("content", "")) > 50]
    with_replies = [p for p in posts if p.get("replies", 0) > 0]
    dates = [p["date"] for p in posts if p.get("date")]

    print(f"\n  保存: {filepath}")
    print(f"  统计: {len(posts)}帖 | {len(with_content)}有内容 | {len(with_replies)}有回帖")
    if dates:
        print(f"  日期: {min(dates)} ~ {max(dates)}")
    print(f"  预览:")
    for p in posts[:5]:
        r = p.get("replies", 0) or 0
        print(f"    [{p.get('date','?')}] {p['title'][:60]} ({r}回复)")


if __name__ == "__main__":
    keyword = ""
    pages = 1
    days = 30
    forum_id = None

    # 解析参数
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--all":
            keyword = ""; i += 1
        elif a == "--forum" and i + 1 < len(args):
            forum_id = args[i + 1]
            if forum_id in FORUMS:
                print(f"  版块: {FORUMS[forum_id]}")
            i += 2
        elif a == "--list":
            print("  可用版块:")
            for fid, fname in FORUMS.items():
                print(f"    --forum {fid}  ->  {fname}")
            sys.exit(0)
        elif a.isdigit():
            pages = int(a); i += 1
        elif not a.startswith("--"):
            keyword = a; i += 1
        else:
            i += 1

    # 如果没有指定关键词且不是--all，用--all
    if not keyword and "--all" not in sys.argv:
        keyword = ""

    mode = f"关键词: {keyword}" if keyword else "全部(无筛选)"
    forum_info = f"版块: {FORUMS.get(forum_id, '全部')}" if forum_id else "全部版块"
    print(f"\n  [UG爱好者论坛] {mode} | {forum_info}")
    print(f"  {pages}页 | {days}天内\n")
    posts = crawl(keyword, pages, days, forum_id)
    save(posts, keyword or "all")
