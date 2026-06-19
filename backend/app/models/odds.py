"""
赔率数据模型 - 简化版
"""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, SmallInteger, DECIMAL
from sqlalchemy.sql import func
from app.database import Base


class Odds(Base):
    """赔率数据表"""
    __tablename__ = "odds"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(String(50), nullable=False)
    bookmaker = Column(String(50), nullable=False)
    home_odds = Column(DECIMAL(6, 3))
    draw_odds = Column(DECIMAL(6, 3))
    away_odds = Column(DECIMAL(6, 3))
    handicap = Column(DECIMAL(4, 2))
    is_opening = Column(SmallInteger, default=0)
    collect_time = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "bookmaker": self.bookmaker,
            "home_odds": float(self.home_odds) if self.home_odds else None,
            "draw_odds": float(self.draw_odds) if self.draw_odds else None,
            "away_odds": float(self.away_odds) if self.away_odds else None,
            "handicap": float(self.handicap) if self.handicap else None,
            "is_opening": bool(self.is_opening)
        }
