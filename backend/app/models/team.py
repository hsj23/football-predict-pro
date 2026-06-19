"""
球队数据模型 - 简化版
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Team(Base):
    """球队信息表"""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(50), unique=True, nullable=False)
    team_name = Column(String(100), nullable=False)
    league_name = Column(String(100))
    ranking = Column(Integer)
    points = Column(Integer)

    def to_dict(self):
        return {
            "id": self.id,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "league_name": self.league_name,
            "ranking": self.ranking,
            "points": self.points
        }
