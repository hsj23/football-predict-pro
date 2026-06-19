"""
爬虫初始化
"""
from crawlers.base_crawler import BaseCrawler
from crawlers.platforms.leisu import LeisuCrawler
from crawlers.platforms.wubai import WuBaiCrawler
from crawlers.platforms.flashscore import FlashScoreCrawler

# 平台映射
CRAWLERS = {
    "leisu": LeisuCrawler,
    "wubai": WuBaiCrawler,
    "flashscore": FlashScoreCrawler
}


def get_crawler(platform: str) -> BaseCrawler:
    """获取爬虫实例"""
    crawler_class = CRAWLERS.get(platform)
    if crawler_class:
        return crawler_class()
    raise ValueError(f"不支持的爬虫平台: {platform}")


__all__ = [
    "BaseCrawler",
    "LeisuCrawler",
    "WuBaiCrawler",
    "FlashScoreCrawler",
    "CRAWLERS",
    "get_crawler"
]
