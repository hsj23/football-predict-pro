"""
雷速体育爬虫
"""
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from crawlers.base_crawler import BaseCrawler


class LeisuCrawler(BaseCrawler):
    """雷速体育爬虫"""

    BASE_URL = "https://www.leisu.com"

    def __init__(self):
        super().__init__()
        self.name = "雷速体育"

    def crawl_matches(self, date: str = None) -> List[Dict]:
        """
        爬取比赛列表

        Args:
            date: 日期格式 YYYY-MM-DD，默认今天
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.BASE_URL}/data/football/detail"

        # 雷速体育API
        api_url = f"{self.BASE_URL}/api/football/list"

        matches = []

        try:
            response = self.get(api_url, params={
                "date": date,
                "type": "all"
            })

            if response and response.status_code == 200:
                data = response.json()

                if data.get("code") == 200:
                    for match_data in data.get("data", {}).get("list", []):
                        match = self._parse_match(match_data)
                        if match:
                            matches.append(match)

        except Exception as e:
            print(f"雷速体育爬取比赛失败: {e}")

        return matches

    def _parse_match(self, data: Dict) -> Optional[Dict]:
        """解析比赛数据"""
        try:
            return {
                "match_id": str(data.get("id", "")),
                "league_name": data.get("league_name", ""),
                "home_team_name": data.get("home_team_name", ""),
                "away_team_name": data.get("away_team_name", ""),
                "match_time": data.get("match_time", ""),
                "status": data.get("status", "scheduled"),
                "home_score": data.get("home_score"),
                "away_score": data.get("away_score"),
                "source": "leisu"
            }
        except Exception:
            return None

    def crawl_odds(self, match_id: str) -> Dict:
        """
        爬取赔率数据

        Args:
            match_id: 比赛ID
        """
        odds_data = {
            "match_id": match_id,
            "source": "leisu",
            "european": [],
            "asian": []
        }

        try:
            # 欧赔API
            euro_url = f"{self.BASE_URL}/api/odds/european/{match_id}"
            response = self.get(euro_url)

            if response and response.status_code == 200:
                data = response.json()
                for item in data.get("data", []):
                    odds_data["european"].append({
                        "bookmaker": item.get("company_name", ""),
                        "home_odds": item.get("home_odds"),
                        "draw_odds": item.get("draw_odds"),
                        "away_odds": item.get("away_odds"),
                        "is_opening": item.get("is_opening", 0)
                    })

            # 亚盘API
            asian_url = f"{self.BASE_URL}/api/odds/asian/{match_id}"
            response = self.get(asian_url)

            if response and response.status_code == 200:
                data = response.json()
                for item in data.get("data", []):
                    odds_data["asian"].append({
                        "bookmaker": item.get("company_name", ""),
                        "handicap": item.get("handicap"),
                        "home_water": item.get("home_water"),
                        "away_water": item.get("away_water"),
                        "is_opening": item.get("is_opening", 0)
                    })

        except Exception as e:
            print(f"雷速体育爬取赔率失败: {e}")

        return odds_data

    def crawl_predictions(self, match_id: str) -> List[Dict]:
        """
        爬取预测数据

        Args:
            match_id: 比赛ID
        """
        predictions = []

        try:
            url = f"{self.BASE_URL}/api/prediction/{match_id}"
            response = self.get(url)

            if response and response.status_code == 200:
                data = response.json()

                for item in data.get("data", []):
                    prediction = {
                        "match_id": match_id,
                        "source_platform": "leisu",
                        "prediction_result": self._parse_prediction_result(item.get("result", "")),
                        "confidence": item.get("confidence"),
                        "predicted_score": item.get("score"),
                        "source_accuracy": item.get("accuracy"),
                        "expert_name": item.get("expert_name", ""),
                        "collect_time": datetime.now().isoformat()
                    }
                    predictions.append(prediction)

        except Exception as e:
            print(f"雷速体育爬取预测失败: {e}")

        return predictions

    def _parse_prediction_result(self, result: str) -> str:
        """解析预测结果"""
        result_map = {
            "主胜": "home",
            "平": "draw",
            "客胜": "away",
            "胜": "home",
            "负": "away"
        }
        return result_map.get(result, result.lower())

    def crawl_team_form(self, team_id: str) -> List[Dict]:
        """
        爬取球队近期战绩

        Args:
            team_id: 球队ID
        """
        forms = []

        try:
            url = f"{self.BASE_URL}/api/team/form/{team_id}"
            response = self.get(url)

            if response and response.status_code == 200:
                data = response.json()

                for item in data.get("data", [])[:10]:  # 取最近10场
                    form = {
                        "team_id": team_id,
                        "match_date": item.get("match_date"),
                        "opponent_name": item.get("opponent_name"),
                        "is_home": item.get("is_home", 0),
                        "goals_for": item.get("goals_for"),
                        "goals_against": item.get("goals_against"),
                        "result": item.get("result"),  # W/D/L
                        "competition": item.get("competition", "")
                    }
                    forms.append(form)

        except Exception as e:
            print(f"雷速体育爬取球队战绩失败: {e}")

        return forms
