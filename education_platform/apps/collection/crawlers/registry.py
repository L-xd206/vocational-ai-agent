from .mohrss import MohrssCrawler


# 数据库 CrawlSource.code 与采集器实现之间的唯一映射入口。
# 未来增加网站时，只需实现新的 Crawler 并在这里注册。
CRAWLER_REGISTRY = {
    "mohrss": MohrssCrawler,
}


def get_crawler(source):
    crawler_class = CRAWLER_REGISTRY.get(source.code)
    if crawler_class is None:
        raise ValueError(
            f"尚未实现采集来源“{source.name}”（编码：{source.code}）对应的采集器"
        )
    return crawler_class()


def validate_crawler_code(code):
    if code not in CRAWLER_REGISTRY:
        raise ValueError(f"来源编码“{code}”尚未实现对应采集器")

