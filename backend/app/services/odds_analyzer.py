"""
赔率分析服务
"""
from sqlalchemy.orm import Session
from typing import Dict, List
from datetime import datetime
from app.models.odds import Odds, OddsHistory


class OddsAnalyzer:
    """赔率分析器"""

    def __init__(self, db: Session):
        self.db = db

    def analyze(self, match_id: str) -> Dict:
        """综合赔率分析"""
        odds = self.db.query(Odds).filter(Odds.match_id == match_id).all()

        if not odds:
            return {"error": "暂无赔率数据"}

        return {
            "match_id": match_id,
            "kelly_analysis": self._kelly_analysis(odds),
            "odds_change_analysis": self._odds_change_analysis(match_id),
            "bookmaker_comparison": self._bookmaker_comparison(odds),
            "anomaly_detection": self._detect_anomalies(odds)
        }

    def _kelly_analysis(self, odds: List[Odds]) -> Dict:
        """凯利指数分析"""
        results = []

        for o in odds:
            if not (o.home_odds and o.draw_odds and o.away_odds):
                continue

            home_odds = float(o.home_odds)
            draw_odds = float(o.draw_odds)
            away_odds = float(o.away_odds)

            # 计算返还率
            return_rate = 1/home_odds + 1/draw_odds + 1/away_odds

            # 计算凯利指数
            kelly_home = (1/home_odds) / return_rate
            kelly_draw = (1/draw_odds) / return_rate
            kelly_away = (1/away_odds) / return_rate

            # 判断价值
            kelly_values = {
                "home": kelly_home,
                "draw": kelly_draw,
                "away": kelly_away
            }
            value_bet = [k for k, v in kelly_values.items() if v > 0.35]

            results.append({
                "bookmaker": o.bookmaker,
                "return_rate": round((1 - return_rate) * 100, 2),
                "kelly_index": {
                    "home": round(kelly_home * 100, 2),
                    "draw": round(kelly_draw * 100, 2),
                    "away": round(kelly_away * 100, 2)
                },
                "value_bet": value_bet,
                "interpretation": self._interpret_kelly(kelly_home, kelly_draw, kelly_away)
            })

        return {
            "results": results,
            "explanation": "凯利指数>35%表示该结果有投注价值"
        }

    def _interpret_kelly(self, home: float, draw: float, away: float) -> str:
        """解释凯利指数"""
        max_kelly = max(home, draw, away)

        if max_kelly == home:
            if home > 0.35:
                return "主胜有投注价值"
            return "庄家看好主胜"
        elif max_kelly == draw:
            if draw > 0.35:
                return "平局有投注价值"
            return "庄家看好平局"
        else:
            if away > 0.35:
                return "客胜有投注价值"
            return "庄家看好客胜"

    def _odds_change_analysis(self, match_id: str) -> Dict:
        """赔率变化分析"""
        changes = []

        # 获取每个公司的赔率变化
        bookmakers = self.db.query(Odds.bookmaker).filter(
            Odds.match_id == match_id
        ).distinct().all()

        for (bookmaker,) in bookmakers:
            history = self.db.query(OddsHistory).filter(
                OddsHistory.match_id == match_id,
                OddsHistory.bookmaker == bookmaker
            ).order_by(OddsHistory.record_time).all()

            if len(history) >= 2:
                first = history[0]
                last = history[-1]

                home_change = float(last.home_odds) - float(first.home_odds) if last.home_odds and first.home_odds else 0
                draw_change = float(last.draw_odds) - float(first.draw_odds) if last.draw_odds and first.draw_odds else 0
                away_change = float(last.away_odds) - float(first.away_odds) if last.away_odds and first.away_odds else 0

                # 判断变化趋势
                if home_change < -0.1:
                    trend = "主胜赔率下降，主胜热度增加"
                elif away_change < -0.1:
                    trend = "客胜赔率下降，客胜热度增加"
                elif draw_change < -0.1:
                    trend = "平局赔率下降，平局热度增加"
                else:
                    trend = "赔率相对稳定"

                changes.append({
                    "bookmaker": bookmaker,
                    "home_change": round(home_change, 3),
                    "draw_change": round(draw_change, 3),
                    "away_change": round(away_change, 3),
                    "trend": trend
                })

        return {
            "changes": changes,
            "explanation": "负值表示赔率下降，正值表示赔率上升"
        }

    def _bookmaker_comparison(self, odds: List[Odds]) -> Dict:
        """博彩公司赔率对比"""
        opening_odds = [o for o in odds if o.is_opening == 1]

        if not opening_odds:
            return {"message": "暂无初盘赔率"}

        comparison = []
        for o in opening_odds:
            if o.home_odds and o.draw_odds and o.away_odds:
                comparison.append({
                    "bookmaker": o.bookmaker,
                    "home_odds": float(o.home_odds),
                    "draw_odds": float(o.draw_odds),
                    "away_odds": float(o.away_odds)
                })

        # 计算平均值
        avg_home = sum(c["home_odds"] for c in comparison) / len(comparison)
        avg_draw = sum(c["draw_odds"] for c in comparison) / len(comparison)
        avg_away = sum(c["away_odds"] for c in comparison) / len(comparison)

        # 找出最高赔率
        max_home = max(comparison, key=lambda x: x["home_odds"])
        max_draw = max(comparison, key=lambda x: x["draw_odds"])
        max_away = max(comparison, key=lambda x: x["away_odds"])

        return {
            "average_odds": {
                "home": round(avg_home, 3),
                "draw": round(avg_draw, 3),
                "away": round(avg_away, 3)
            },
            "best_odds": {
                "home": max_home,
                "draw": max_draw,
                "away": max_away
            },
            "all_bookmakers": comparison
        }

    def _detect_anomalies(self, odds: List[Odds]) -> Dict:
        """检测赔率异常"""
        anomalies = []

        opening_odds = [o for o in odds if o.is_opening == 1]
        if len(opening_odds) < 2:
            return {"anomalies": [], "message": "数据不足，无法检测异常"}

        # 计算平均赔率
        home_odds_list = [float(o.home_odds) for o in opening_odds if o.home_odds]
        draw_odds_list = [float(o.draw_odds) for o in opening_odds if o.draw_odds]
        away_odds_list = [float(o.away_odds) for o in opening_odds if o.away_odds]

        avg_home = sum(home_odds_list) / len(home_odds_list) if home_odds_list else 0
        avg_draw = sum(draw_odds_list) / len(draw_odds_list) if draw_odds_list else 0
        avg_away = sum(away_odds_list) / len(away_odds_list) if away_odds_list else 0

        # 检测偏离平均值较大的赔率
        threshold = 0.1  # 10%偏差阈值

        for o in opening_odds:
            if o.home_odds and abs(float(o.home_odds) - avg_home) / avg_home > threshold:
                anomalies.append({
                    "bookmaker": o.bookmaker,
                    "type": "主胜赔率异常",
                    "value": float(o.home_odds),
                    "average": round(avg_home, 3),
                    "deviation": round((float(o.home_odds) - avg_home) / avg_home * 100, 1)
                })

            if o.draw_odds and abs(float(o.draw_odds) - avg_draw) / avg_draw > threshold:
                anomalies.append({
                    "bookmaker": o.bookmaker,
                    "type": "平局赔率异常",
                    "value": float(o.draw_odds),
                    "average": round(avg_draw, 3),
                    "deviation": round((float(o.draw_odds) - avg_draw) / avg_draw * 100, 1)
                })

            if o.away_odds and abs(float(o.away_odds) - avg_away) / avg_away > threshold:
                anomalies.append({
                    "bookmaker": o.bookmaker,
                    "type": "客胜赔率异常",
                    "value": float(o.away_odds),
                    "average": round(avg_away, 3),
                    "deviation": round((float(o.away_odds) - avg_away) / avg_away * 100, 1)
                })

        return {
            "anomalies": anomalies,
            "message": "异常赔率可能意味着庄家对比赛有不同的看法" if anomalies else "未发现明显异常赔率"
        }
