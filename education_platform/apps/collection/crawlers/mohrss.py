from .base import BaseCrawler


SEARCH_PATH = "/cjobs/jobinfolist/listJobinfolist"


class MohrssCrawler(BaseCrawler):
    """中国公共招聘网采集器。"""

    def crawl(self, *, job, source):
        # 暂时复用项目中已经验证过的公共招聘网请求与解析函数。
        from apps.collection.tasks import crawl_single_job

        config = source.config_json or {}
        try:
            pages = int(config.get("pages", 3))
        except (TypeError, ValueError):
            pages = 3
        pages = max(1, min(pages, 10))
        try:
            timeout = int(config.get("timeout", 20))
        except (TypeError, ValueError):
            timeout = 20
        timeout = max(5, min(timeout, 60))

        search_url = source.base_url.rstrip("/") + SEARCH_PATH

        result = crawl_single_job(
            {
                "name": job.name,
                "search_keywords": job.search_keywords or [job.name],
            },
            pages=pages,
            search_url=search_url,
            timeout=timeout,
        )
        return result.get("results", [])
