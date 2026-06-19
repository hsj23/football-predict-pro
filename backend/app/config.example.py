"""
配置文件示例
复制此文件为 config.py 并修改为你的实际配置
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 数据库配置 - 修改为你的MySQL配置
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://用户名:密码@localhost:3306/football_predict")

# Redis配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# API配置
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
API_DEBUG = os.getenv("API_DEBUG", "true").lower() == "true"

# 爬虫配置
CRAWLER_DELAY = 2  # 请求间隔(秒)
CRAWLER_TIMEOUT = 30  # 请求超时(秒)
PROXY_ENABLED = False  # 是否启用代理
PROXY_URL = os.getenv("PROXY_URL", "")

# 数据源配置
DATA_SOURCES = {
    "leisu": {
        "name": "雷速体育",
        "base_url": "https://www.leisu.com",
        "enabled": True
    },
    "wubai": {
        "name": "500彩票网",
        "base_url": "https://www.500.com",
        "enabled": True
    },
    "flashscore": {
        "name": "FlashScore",
        "base_url": "https://www.flashscore.com",
        "enabled": True
    },
    "williamhill": {
        "name": "威廉希尔",
        "base_url": "https://www.williamhill.com",
        "enabled": False
    }
}

# 博彩公司配置
BOOKMAKERS = {
    "williamhill": {"name": "威廉希尔", "type": "european"},
    "ladbrokes": {"name": "立博", "type": "european"},
    "bet365": {"name": "Bet365", "type": "asian"},
    "macau": {"name": "澳门彩票", "type": "asian"},
    "crown": {"name": "皇冠", "type": "asian"},
    "betfair": {"name": "必发", "type": "exchange"}
}

# 联赛配置
LEAGUES = {
    "en_premier_league": {"name": "英超", "country": "英格兰"},
    "es_la_liga": {"name": "西甲", "country": "西班牙"},
    "de_bundesliga": {"name": "德甲", "country": "德国"},
    "it_serie_a": {"name": "意甲", "country": "意大利"},
    "fr_ligue_1": {"name": "法甲", "country": "法国"},
    "cn_super_league": {"name": "中超", "country": "中国"},
    "uefa_champions_league": {"name": "欧冠", "country": "欧洲"},
    "uefa_europa_league": {"name": "欧联杯", "country": "欧洲"}
}

# 机器学习配置
ML_CONFIG = {
    "model_type": "xgboost",
    "train_test_split": 0.2,
    "cross_validation_folds": 5,
    "feature_importance_threshold": 0.01,
    "min_samples_for_training": 1000
}
