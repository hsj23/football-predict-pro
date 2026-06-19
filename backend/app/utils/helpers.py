"""
工具函数
"""
from datetime import datetime
from typing import Optional


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """格式化日期时间"""
    if not dt:
        return ""
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """解析日期时间字符串"""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, fmt)
    except ValueError:
        return None


def calculate_win_rate(wins: int, total: int) -> float:
    """计算胜率"""
    if total == 0:
        return 0.0
    return round(wins / total * 100, 1)


def format_odds(odds: float) -> str:
    """格式化赔率"""
    if odds is None:
        return "-"
    return f"{odds:.3f}"


def get_result_chinese(result: str) -> str:
    """获取结果中文名"""
    mapping = {
        "home": "主胜",
        "draw": "平局",
        "away": "客胜",
        "W": "胜",
        "D": "平",
        "L": "负"
    }
    return mapping.get(result, result)
