"""
预测引擎 - 核心预测分析服务
"""
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime
from collections import Counter
from app.models.match import Match
from app.models.odds import Odds
from app.models.prediction import Prediction
from app.models.team import Team, TeamForm


class PredictionEngine:
    """综合预测引擎"""

    def __init__(self, db: Session):
        self.db = db

    def analyze_match(self, match_id: str) -> Dict:
        """综合分析比赛"""
        # 获取比赛信息
        match = self.db.query(Match).filter(Match.match_id == match_id).first()
        if not match:
            return {"error": "比赛不存在"}

        # 多维度分析
        result = {
            "match_id": match_id,
            "match_info": match.to_dict(),
            "analysis_time": datetime.now().isoformat(),
            "predictions": {}
        }

        # 1. 多平台预测聚合
        platform_analysis = self._analyze_platform_predictions(match_id)
        result["predictions"]["platform_aggregation"] = platform_analysis

        # 2. 赔率分析
        odds_analysis = self._analyze_odds(match_id)
        result["predictions"]["odds_analysis"] = odds_analysis

        # 3. 球队状态分析
        team_analysis = self._analyze_team_form(match)
        result["predictions"]["team_analysis"] = team_analysis

        # 4. 综合预测
        final_prediction = self._generate_final_prediction(result)
        result["final_prediction"] = final_prediction

        return result

    def _analyze_platform_predictions(self, match_id: str) -> Dict:
        """分析各平台预测"""
        predictions = self.db.query(Prediction).filter(
            Prediction.match_id == match_id
        ).all()

        if not predictions:
            return {"message": "暂无平台预测数据"}

        # 统计各结果数量
        result_counter = Counter(p.prediction_result for p in predictions if p.prediction_result)
        total = sum(result_counter.values())

        # 按平台分组
        platform_details = []
        for p in predictions:
            platform_details.append({
                "platform": p.source_platform,
                "prediction": p.prediction_result,
                "confidence": float(p.confidence) if p.confidence else None,
                "accuracy": float(p.source_accuracy) if p.source_accuracy else None
            })

        # 计算加权预测（根据平台准确率）
        weighted_scores = {"home": 0, "draw": 0, "away": 0}
        total_weight = 0

        for p in predictions:
            if p.prediction_result and p.source_accuracy:
                weight = float(p.source_accuracy) / 100
                weighted_scores[p.prediction_result] += weight
                total_weight += weight

        if total_weight > 0:
            weighted_prediction = max(weighted_scores, key=weighted_scores.get)
        else:
            weighted_prediction = result_counter.most_common(1)[0][0] if result_counter else None

        return {
            "total_platforms": len(predictions),
            "result_distribution": {
                "home": result_counter.get("home", 0),
                "draw": result_counter.get("draw", 0),
                "away": result_counter.get("away", 0)
            },
            "percentages": {
                "home": round(result_counter.get("home", 0) / total * 100, 1) if total > 0 else 0,
                "draw": round(result_counter.get("draw", 0) / total * 100, 1) if total > 0 else 0,
                "away": round(result_counter.get("away", 0) / total * 100, 1) if total > 0 else 0
            },
            "weighted_prediction": weighted_prediction,
            "platform_details": platform_details
        }

    def _analyze_odds(self, match_id: str) -> Dict:
        """分析赔率"""
        odds = self.db.query(Odds).filter(
            Odds.match_id == match_id
        ).all()

        if not odds:
            return {"message": "暂无赔率数据"}

        # 获取初盘赔率
        opening_odds = [o for o in odds if o.is_opening == 1]
        live_odds = [o for o in odds if o.is_opening == 0]

        analysis = {
            "opening_odds": [],
            "odds_change": []
        }

        # 分析初盘赔率
        for o in opening_odds:
            if o.home_odds and o.draw_odds and o.away_odds:
                # 计算返还率
                return_rate = 1/float(o.home_odds) + 1/float(o.draw_odds) + 1/float(o.away_odds)
                profit_margin = round((1 - return_rate) * 100, 2)

                # 根据赔率判断倾向
                min_odds = min(float(o.home_odds), float(o.draw_odds), float(o.away_odds))
                if min_odds == float(o.home_odds):
                    tendency = "home"
                elif min_odds == float(o.away_odds):
                    tendency = "away"
                else:
                    tendency = "draw"

                analysis["opening_odds"].append({
                    "bookmaker": o.bookmaker,
                    "home_odds": float(o.home_odds),
                    "draw_odds": float(o.draw_odds),
                    "away_odds": float(o.away_odds),
                    "profit_margin": profit_margin,
                    "tendency": tendency
                })

        # 分析赔率变化
        for bookmaker in set(o.bookmaker for o in odds):
            bookmaker_odds = [o for o in odds if o.bookmaker == bookmaker]
            if len(bookmaker_odds) > 1:
                opening = next((o for o in bookmaker_odds if o.is_opening == 1), None)
                latest = next((o for o in reversed(bookmaker_odds) if o.is_opening == 0), None)

                if opening and latest and opening.home_odds and latest.home_odds:
                    analysis["odds_change"].append({
                        "bookmaker": bookmaker,
                        "home_change": round(float(latest.home_odds) - float(opening.home_odds), 3),
                        "draw_change": round(float(latest.draw_odds) - float(opening.draw_odds), 3) if latest.draw_odds and opening.draw_odds else None,
                        "away_change": round(float(latest.away_odds) - float(opening.away_odds), 3) if latest.away_odds and opening.away_odds else None
                    })

        return analysis

    def _analyze_team_form(self, match: Match) -> Dict:
        """分析球队状态"""
        analysis = {
            "home_team": None,
            "away_team": None
        }

        # 获取主队状态
        if match.home_team_name:
            home_forms = self.db.query(TeamForm).filter(
                TeamForm.team_id == match.home_team_name
            ).order_by(TeamForm.match_date.desc()).limit(10).all()

            if home_forms:
                wins = sum(1 for f in home_forms if f.result == "W")
                draws = sum(1 for f in home_forms if f.result == "D")
                losses = sum(1 for f in home_forms if f.result == "L")

                analysis["home_team"] = {
                    "name": match.home_team_name,
                    "recent_form": [f.result for f in home_forms[:5]],
                    "stats": {
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "win_rate": round(wins / len(home_forms) * 100, 1) if home_forms else 0
                    }
                }

        # 获取客队状态
        if match.away_team_name:
            away_forms = self.db.query(TeamForm).filter(
                TeamForm.team_id == match.away_team_name
            ).order_by(TeamForm.match_date.desc()).limit(10).all()

            if away_forms:
                wins = sum(1 for f in away_forms if f.result == "W")
                draws = sum(1 for f in away_forms if f.result == "D")
                losses = sum(1 for f in away_forms if f.result == "L")

                analysis["away_team"] = {
                    "name": match.away_team_name,
                    "recent_form": [f.result for f in away_forms[:5]],
                    "stats": {
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "win_rate": round(wins / len(away_forms) * 100, 1) if away_forms else 0
                    }
                }

        return analysis

    def _generate_final_prediction(self, analysis: Dict) -> Dict:
        """生成最终预测 - 优先使用HybridPredictor"""
        # 尝试使用混合预测器（ML模型 + 赔率 + 外部共识）
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            from ml.hybrid_predictor import HybridPredictor
            predictor = HybridPredictor()

            match_info = analysis.get("match_info", {})
            home = match_info.get("home_team_name", "")
            away = match_info.get("away_team_name", "")
            league = match_info.get("league_name", "")

            # 获取赔率
            odds = None
            odds_analysis = analysis["predictions"].get("odds_analysis", {})
            if odds_analysis.get("opening_odds"):
                first_odds = odds_analysis["opening_odds"][0]
                odds = [
                    float(first_odds.get("home_odds", 2.5)),
                    float(first_odds.get("draw_odds", 3.2)),
                    float(first_odds.get("away_odds", 2.8)),
                ]

            if home and away:
                result = predictor.predict(home, away, league, odds)
                return {
                    "prediction": result["prediction"],
                    "confidence": result["confidence"],
                    "probabilities": result["probabilities"],
                    "confidence_level": result["confidence_level"],
                    "prediction_name": result["prediction_name"],
                    "has_odds": result.get("has_odds", False),
                    "engine": "hybrid",
                    "components": result.get("components", {})
                }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"混合预测器不可用，使用传统方法: {e}")

        # 降级：传统预测方法
        scores = {"home": 0, "draw": 0, "away": 0}
        weights = {
            "platform": 0.4,
            "odds": 0.35,
            "team": 0.25
        }

        platform = analysis["predictions"].get("platform_aggregation", {})
        if "percentages" in platform:
            scores["home"] += platform["percentages"]["home"] * weights["platform"]
            scores["draw"] += platform["percentages"]["draw"] * weights["platform"]
            scores["away"] += platform["percentages"]["away"] * weights["platform"]

        odds = analysis["predictions"].get("odds_analysis", {})
        if "opening_odds" in odds and odds["opening_odds"]:
            from collections import Counter
            tendencies = [o["tendency"] for o in odds["opening_odds"]]
            if tendencies:
                tendency_counter = Counter(tendencies)
                total = sum(tendency_counter.values())
                for t, count in tendency_counter.items():
                    scores[t] += (count / total * 100) * weights["odds"]

        team = analysis["predictions"].get("team_analysis", {})
        home_win_rate = 0
        away_win_rate = 0
        if team.get("home_team"):
            home_win_rate = team["home_team"]["stats"]["win_rate"]
        if team.get("away_team"):
            away_win_rate = team["away_team"]["stats"]["win_rate"]

        if home_win_rate > away_win_rate + 10:
            scores["home"] += 60 * weights["team"]
            scores["draw"] += 25 * weights["team"]
            scores["away"] += 15 * weights["team"]
        elif away_win_rate > home_win_rate + 10:
            scores["home"] += 20 * weights["team"]
            scores["draw"] += 25 * weights["team"]
            scores["away"] += 55 * weights["team"]
        else:
            scores["home"] += 35 * weights["team"]
            scores["draw"] += 30 * weights["team"]
            scores["away"] += 35 * weights["team"]

        total = sum(scores.values())
        if total > 0:
            scores = {k: round(v / total * 100, 1) for k, v in scores.items()}

        final_result = max(scores, key=scores.get)
        confidence = scores[final_result]

        return {
            "prediction": final_result,
            "confidence": confidence,
            "probabilities": scores,
            "confidence_level": "高" if confidence > 50 else "中" if confidence > 40 else "低",
            "engine": "traditional"
        }
