from abc import ABC, abstractmethod


class BaseCrawler(ABC):
    """所有招聘网站采集器都必须实现的统一接口。"""

    @abstractmethod
    def crawl(self, *, job, source):
        """返回经过标准化的招聘信息字典列表。"""
        raise NotImplementedError

