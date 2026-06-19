"""
预测器模块
"""
import numpy as np
from typing import Dict, Optional
from ml.feature_engineering import FeatureEngineer
import logging

logger = logging.getLogger(__name__)


class Predictor:
    """比赛预测器"""

    def __init__(self, model_path: str = None):
        self.model = None
        self.scaler = None
        self.feature_engineer = FeatureEngineer()

        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str):
        """加载模型"""
        import pickle
        try:
            with open(model_path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
            logger.info(f"模型加载成功: {model_path}")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")

    def predict(self, match_data: Dict, odds_data: Dict, team_form: Dict) -> Dict:
        """
        预测比赛结果

        Args:
            match_data: 比赛信息
            odds_data: 赔率数据
            team_form: 球队状态

        Returns:
            预测结果
        """
        if not self.model:
            return {"error": "模型未加载"}

        # 提取特征
        features = self.feature_engineer.extract_features(match_data, odds_data, team_form)
        features = features.reshape(1, -1)

        # 标准化
        if self.scaler:
            features = self.scaler.transform(features)

        # 预测
        prediction = self.model.predict(features)[0]
        probabilities = self.model.predict_proba(features)[0]

        result_map = {0: "home", 1: "draw", 2: "away"}
        result_name_map = {"home": "主胜", "draw": "平局", "away": "客胜"}

        predicted_result = result_map[prediction]

        return {
            "prediction": predicted_result,
            "prediction_name": result_name_map[predicted_result],
            "confidence": float(max(probabilities)),
            "probabilities": {
                "home": float(probabilities[0]),
                "draw": float(probabilities[1]),
                "away": float(probabilities[2])
            },
            "confidence_level": self._get_confidence_level(max(probabilities))
        }

    def _get_confidence_level(self, confidence: float) -> str:
        """获取置信度等级"""
        if confidence >= 0.6:
            return "高"
        elif confidence >= 0.45:
            return "中"
        else:
            return "低"

    def predict_batch(self, matches: list) -> list:
        """批量预测"""
        results = []
        for match in matches:
            result = self.predict(
                match.get("match_data", {}),
                match.get("odds_data", {}),
                match.get("team_form", {})
            )
            result["match_id"] = match.get("match_id")
            results.append(result)
        return results
