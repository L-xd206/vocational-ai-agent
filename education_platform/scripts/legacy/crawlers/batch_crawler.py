"""
批量网页抓取脚本 — 将网页转为干净的 Markdown 文件
=================================================
默认使用 requests + html2text（轻量，无需浏览器）。
对 JS 渲染页面自动切换 crawl4ai + Playwright。

安装:
  pip install html2text requests          # 基础模式（推荐，零额外下载）
  pip install crawl4ai && crawl4ai-setup  # JS渲染模式（可选）

用法:
  python batch_crawler.py                          # 内置示例URL
  python batch_crawler.py urls.txt                 # 从文件读取URL列表
  python batch_crawler.py --url "https://xxx.com"  # 抓取单个URL
  python batch_crawler.py urls.txt --js            # 强制使用浏览器渲染
"""
import csv
import hashlib
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import html2text

# ============================================================
#  配置
# ============================================================
OUTPUT_DIR = Path(__file__).resolve().parent / "crawled_data"
INDEX_FILE = OUTPUT_DIR / "index.csv"
PAGE_TIMEOUT = 20        # 请求超时（秒）
REQUEST_DELAY = 0.8      # 请求间隔（秒）
MAX_RETRIES = 2          # 失败重试次数


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def url_to_filename(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest() + ".md"


def load_urls(filepath: str = None) -> list[str]:
    if filepath and os.path.isfile(filepath):
        urls = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line.startswith("http"):
                    urls.append(line)
        if urls:
            print(f"  从文件加载 {len(urls)} 个URL: {filepath}")
            return urls

    # 内置示例
    return [
        "https://www.ugsnx.com/thread-364444-1-1.html",
        "https://www.ugsnx.com/thread-364416-1-1.html",
        "https://www.ugsnx.com/thread-364407-1-1.html",
        "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist",
    ]


# ============================================================
#  核心：HTML → Markdown 转换
# ============================================================
def html_to_markdown(html_text: str, base_url: str = "") -> str:
    """
    将 HTML 转为干净的 Markdown。
    - 自动提取正文区域
    - 去除导航、广告、脚本
    - 保留标题、段落、列表、链接
    """
    # 1. 用 BeautifulSoup 提取正文区域（优先 article/main，排除导航/广告）
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, "lxml")

    # 移除干扰元素（注意：只用精确选择器，避免误删正文）
    # 例如 [class*='ad'] 会误删 thead，[class*='footer'] 会误删帖子脚注
    for tag in soup.select(
        "script, style, nav, iframe, form, "
        "[class='ad'], [class*='ad-'], [class*='ad_'], "  # 广告class，但排除 thead
        "[class*='site-nav'], [class*='site-footer'], "
        "[class*='sidebar'], [class*='banner'], "
        "[class*='recommend'], [class*='related']"
    ):
        tag.decompose()

    # 优先取正文区域
    content_el = None
    for selector in [
        "article", "main",
        "[class*='post']", "[class*='content']", "[class*='detail']",
        "[class*='article']", "[class*='thread']",
        '[id*="postlist"]',   # Discuz! 帖子列表
    ]:
        el = soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 100:
            content_el = el
            break

    # Discuz! 论坛：合并所有 .pct 内容块（帖子正文+回帖）
    is_forum = "ugsnx.com" in base_url or "cmiw.cn" in base_url
    if content_el is None and is_forum:
        pct_divs = soup.select('[class*="pct"]')
        if pct_divs:
            # 把所有pct的内容合并
            combined = soup.new_tag("div")
            for div in pct_divs:
                combined.append(div)
            content_el = combined

    if content_el is None:
        content_el = soup.find("body") or soup

    # 2. html2text 转换
    converter = html2text.HTML2Text()
    converter.body_width = 0          # 不自动换行
    converter.ignore_links = False    # 保留链接
    converter.ignore_images = False   # 保留图片引用
    converter.ignore_emphasis = False # 保留加粗/斜体
    converter.skip_internal_links = False
    converter.single_line_break = False
    converter.mark_code = True

    md = converter.handle(str(content_el))

    # 3. 清理多余空行
    md = re.sub(r"\n{4,}", "\n\n\n", md)
    md = md.strip()

    return md


# ============================================================
#  抓取单页
# ============================================================
def fetch_page(url: str, session: requests.Session, use_js: bool = False) -> dict:
    """
    抓取单个 URL
    返回: {url, filename, status, error, content_length, crawl_time, title}
    """
    result = {
        "url": url,
        "filename": url_to_filename(url),
        "status": "fail",
        "error": "",
        "content_length": 0,
        "crawl_time": "",
        "title": "",
    }
    start = time.time()
    html_text = ""

    # ---- 方式1: requests (快速，适用于99%的传统网页) ----
    if not use_js:
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = session.get(
                    url,
                    timeout=PAGE_TIMEOUT,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 Chrome/120.0.0.0"
                        ),
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    },
                )
                resp.raise_for_status()

                # 自动检测编码（优先用服务器返回的，其次自动检测）
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                html_text = resp.text
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    time.sleep(1)
                else:
                    result["error"] = f"HTTP: {e}"
                    result["crawl_time"] = f"{time.time() - start:.1f}s"
                    return result

    # ---- 方式2: Playwright (JS渲染页面) ----
    else:
        try:
            html_text = _fetch_with_playwright(url)
        except Exception as e:
            result["error"] = f"Browser: {e}"
            result["crawl_time"] = f"{time.time() - start:.1f}s"
            return result

    if not html_text:
        result["error"] = "页面内容为空"
        result["crawl_time"] = f"{time.time() - start:.1f}s"
        return result

    # ---- 转 Markdown ----
    try:
        md_content = html_to_markdown(html_text, url)

        # 提取标题
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
        if title_match:
            result["title"] = title_match.group(1).strip()[:200]

        # 保存文件
        filepath = OUTPUT_DIR / result["filename"]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {result['title'] or url}\n\n")
            f.write(f"> URL: {url}\n")
            f.write(f"> 抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 内容长度: {len(md_content)} 字符\n\n")
            f.write("---\n\n")
            f.write(md_content)

        result["status"] = "success"
        result["content_length"] = len(md_content)
        result["crawl_time"] = f"{time.time() - start:.1f}s"
    except Exception as e:
        result["error"] = f"转换失败: {e}"
        result["crawl_time"] = f"{time.time() - start:.1f}s"

    return result


def _fetch_with_playwright(url: str) -> str:
    """使用 Playwright + 系统 Edge 渲染页面（需要 crawl4ai 已安装）"""
    import asyncio

    async def _run():
        from crawl4ai import AsyncWebCrawler, CacheMode, BrowserConfig

        browser_cfg = BrowserConfig(
            browser_type="chromium",
            channel="msedge",
            headless=True,
            verbose=False,
        )
        async with AsyncWebCrawler(config=browser_cfg, verbose=False) as crawler:
            result = await crawler.arun(
                url=url,
                cache_mode=CacheMode.BYPASS,
                word_count_threshold=10,
                remove_overlay_elements=True,
                page_timeout=30000,
            )
            if result.success:
                return result.html or ""
            raise Exception(result.error_message or "浏览器渲染失败")

    return asyncio.run(_run())


# ============================================================
#  批量抓取主函数
# ============================================================
def _bypass_ugsnx_captcha(session: requests.Session):
    """绕过 UG爱好者论坛的数学验证码"""
    try:
        r = session.get("https://www.ugsnx.com/forum-45-1.html", timeout=10)
        m = re.search(r"(\d+)\s*([+\-*/])\s*(\d+)\s*=\s*\?", r.text)
        if not m:
            return
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        ans = a + b if op == "+" else (a - b if op == "-" else (a * b if op == "*" else a // b))
        session.post(
            "https://www.ugsnx.com/forum.php",
            data={"answer": str(ans), "secqsubmit": "Submit"},
            headers={"Referer": "https://www.ugsnx.com/forum-45-1.html"},
            timeout=10,
        )
        print("         [ugsnx] 验证码已绕过", flush=True)
    except Exception:
        pass


def crawl_batch(urls: list[str], use_js: bool = False) -> list[dict]:
    session = requests.Session()

    # 如果URL中有ugsnx，先绕过验证码
    if any("ugsnx.com" in u for u in urls):
        _bypass_ugsnx_captcha(session)

    results = []

    mode = "JS浏览器" if use_js else "HTTP直连"
    print(f"\n  开始抓取 {len(urls)} 个URL | 模式: {mode}")
    print(f"  {'='*55}")

    for i, url in enumerate(urls, 1):
        print(f"  [{i}/{len(urls)}] {url[:70]}", flush=True)

        result = fetch_page(url, session, use_js)
        results.append(result)

        if result["status"] == "success":
            print(f"         [OK] {result['content_length']}字, {result['crawl_time']}")
        else:
            print(f"         [FAIL] {result['error'][:80]}")

        time.sleep(REQUEST_DELAY)

    return results


# ============================================================
#  保存索引
# ============================================================
def save_index(results: list[dict]):
    with open(INDEX_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "url", "filename", "status", "error", "content_length",
            "crawl_time", "title",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    success = sum(1 for r in results if r["status"] == "success")
    total_chars = sum(r["content_length"] for r in results)
    print(f"\n  {'='*55}")
    print(f"  索引: {INDEX_FILE}")
    print(f"  结果: {success}/{len(results)} 成功 | 共 {total_chars} 字")
    print(f"  文件: {OUTPUT_DIR}/")


# ============================================================
#  入口
# ============================================================
def main():
    ensure_dirs()

    args = sys.argv[1:]
    urls = []
    use_js = "--js" in args
    args = [a for a in args if a != "--js"]

    if "--url" in args:
        idx = args.index("--url")
        if idx + 1 < len(args):
            urls = [args[idx + 1]]
    elif args and not args[0].startswith("--"):
        urls = load_urls(args[0])
    else:
        urls = load_urls()

    if not urls:
        print("  没有URL。用法: python batch_crawler.py [urls.txt] [--url URL] [--js]")
        return

    results = crawl_batch(urls, use_js)
    save_index(results)


if __name__ == "__main__":
    print(f"\n  [batch_crawler] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    main()
