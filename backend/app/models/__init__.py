"""
数据模型初始化
"""
from app.models.match import Match
from app.models.odds import Odds
from app.models.prediction import Prediction, PlatformAccuracy
from app.models.team import Team

__all__ = [
    "Match",
    "Odds",
    "Prediction",
    "PlatformAccuracy",
    "Team"
]
