"""
爬虫基类
"""
import time
import random
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from fake_useragent import UserAgent
from app.config import CRAWLER_DELAY, CRAWLER_TIMEOUT, PROXY_ENABLED, PROXY_URL


class BaseCrawler(ABC):
    """爬虫基类"""

    def __init__(self):
        self.session = requests.Session()
        self.ua = UserAgent()
        self.delay = CRAWLER_DELAY
        self.timeout = CRAWLER_TIMEOUT

    def get_headers(self) -> Dict:
        """获取请求头"""
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def get_proxies(self) -> Optional[Dict]:
        """获取代理"""
        if PROXY_ENABLED and PROXY_URL:
            return {"http": PROXY_URL, "https": PROXY_URL}
        return None

    def request(self, url: str, method: str = "GET", **kwargs) -> Optional[requests.Response]:
        """发送请求"""
        try:
            headers = self.get_headers()
            if "headers" in kwargs:
                headers.update(kwargs["headers"])

            proxies = self.get_proxies()

            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=kwargs.get("timeout", self.timeout),
                proxies=proxies,
                **{k: v for k, v in kwargs.items() if k not in ["headers", "timeout"]}
            )

            # 随机延迟
            time.sleep(self.delay + random.random())

            return response

        except requests.RequestException as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """GET请求"""
        return self.request(url, "GET", **kwargs)

    def post(self, url: str, **kwargs) -> Optional[requests.Response]:
        """POST请求"""
        return self.request(url, "POST", **kwargs)

    @abstractmethod
    def crawl_matches(self, date: str = None) -> List[Dict]:
        """爬取比赛列表"""
        pass

    @abstractmethod
    def crawl_odds(self, match_id: str) -> Dict:
        """爬取赔率数据"""
        pass

    @abstractmethod
    def crawl_predictions(self, match_id: str) -> List[Dict]:
        """爬取预测数据"""
        pass
