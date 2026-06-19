"""
预测数据模型 - 简化版
"""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, DECIMAL
from sqlalchemy.sql import func
from app.database import Base


class Prediction(Base):
    """预测数据表"""
    __tablename__ = "predictions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(String(50), nullable=False)
    source_platform = Column(String(50), nullable=False)
    prediction_result = Column(String(10))
    confidence = Column(DECIMAL(5, 2))
    source_accuracy = Column(DECIMAL(5, 2))
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "source_platform": self.source_platform,
            "prediction_result": self.prediction_result,
            "confidence": float(self.confidence) if self.confidence else None,
            "source_accuracy": float(self.source_accuracy) if self.source_accuracy else None
        }


class PlatformAccuracy(Base):
    """平台准确率统计表"""
    __tablename__ = "platform_accuracy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    league = Column(String(50))
    total_predictions = Column(Integer, default=0)
    correct_predictions = Column(Integer, default=0)
    accuracy_rate = Column(DECIMAL(5, 2))


class PredictionHistory(Base):
    """历史预测记录表 - 保存近30天的预测结果"""
    __tablename__ = "prediction_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(String(50), nullable=False, unique=True)
    match_date = Column(DateTime, nullable=False)
    league = Column(String(50))
    home_team = Column(String(100))
    away_team = Column(String(100))
    prediction_result = Column(String(10))  # home/draw/away
    prediction_name = Column(String(20))  # 主胜/平局/客胜
    confidence = Column(DECIMAL(5, 2))
    actual_result = Column(String(10))  # 实际结果
    actual_score = Column(String(20))  # 实际比分
    predicted_score = Column(String(20))  # 预测比分
    is_correct = Column(Integer, default=0)  # 0-未验证/1-正确/2-错误
    home_score = Column(Integer)
    away_score = Column(Integer)
    detail_json = Column(String(10000))  # 缓存完整预测详情JSON
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "match_date": self.match_date.strftime("%Y-%m-%d %H:%M") if self.match_date else None,
            "league": self.league,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "prediction_result": self.prediction_result,
            "prediction_name": self.prediction_name,
            "confidence": float(self.confidence) if self.confidence else None,
            "actual_result": self.actual_result,
            "actual_score": self.actual_score,
            "predicted_score": self.predicted_score,
            "is_correct": self.is_correct,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }
