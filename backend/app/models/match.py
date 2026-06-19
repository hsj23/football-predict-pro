"""
比赛数据模型 - 简化版
"""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Match(Base):
    """比赛信息表"""
    __tablename__ = "matches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(String(50), unique=True, nullable=False)
    league_name = Column(String(100))
    home_team_name = Column(String(100))
    away_team_name = Column(String(100))
    match_time = Column(DateTime)
    status = Column(String(20), default="scheduled")
    home_score = Column(Integer)
    away_score = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "league_name": self.league_name,
            "home_team_name": self.home_team_name,
            "away_team_name": self.away_team_name,
            "match_time": self.match_time.isoformat() if self.match_time else None,
            "status": self.status,
            "home_score": self.home_score,
            "away_score": self.away_score
        }
