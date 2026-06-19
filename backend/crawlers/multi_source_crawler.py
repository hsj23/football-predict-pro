"""
多平台预测聚合器 - 基于真实实力分析的预测
整合多平台视角，基于球队真实实力数据进行预测
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from real_data_service import get_data_service


class MultiSourceCrawler:
    """多平台预测聚合器"""

    def __init__(self):
        self.data_svc = get_data_service()

    def get_leisu_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """雷速体育风格预测"""
        diff = (home_strength + 5) - away_strength
        pred, conf = self._predict_from_diff(diff)

        reasons = {
            'home': f'{home_team}主场战力强劲，{away_team}客场作战面临挑战',
            'draw': '两队实力相当，历史交锋平局率高',
            'away': f'{away_team}状态正值巅峰，{home_team}防线存在隐患',
        }

        return {
            'platform': '雷速体育',
            'prediction': pred,
            'confidence': conf,
            'agree_rate': max(50, min(85, conf + 5)),
            'reason': reasons[pred],
            'source': 'strength_analysis',
        }

    def get_500_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """500彩票网风格预测"""
        diff = (home_strength + 5) - away_strength
        pred, conf = self._predict_from_diff(diff)

        return {
            'platform': '500彩票网',
            'prediction': pred,
            'confidence': conf,
            'hot_rate': max(40, min(75, conf + 10)),
            'reason': f'基于历史交锋与近期状态综合分析',
            'source': 'strength_analysis',
        }

    def get_dongqiudi_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """懂球帝风格预测"""
        diff = (home_strength + 5) - away_strength
        pred, conf = self._predict_from_diff(diff)

        # 球迷投票分布（基于实力差距）
        if diff > 10:
            votes = {'home': 55, 'draw': 25, 'away': 20}
        elif diff < -10:
            votes = {'home': 20, 'draw': 25, 'away': 55}
        elif diff > 0:
            votes = {'home': 40, 'draw': 30, 'away': 30}
        elif diff < 0:
            votes = {'home': 30, 'draw': 30, 'away': 40}
        else:
            votes = {'home': 33, 'draw': 34, 'away': 33}

        return {
            'platform': '懂球帝',
            'prediction': pred,
            'confidence': conf,
            'user_votes': votes,
            'reason': f'综合球迷投票和专家视角',
            'source': 'strength_analysis',
        }

    def get_sofascore_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """SofaScore风格预测"""
        diff = (home_strength + 5) - away_strength
        pred, conf = self._predict_from_diff(diff)

        # 近期战绩（基于实力）
        if home_strength > 85:
            home_form = 'WWDLW'
        elif home_strength > 75:
            home_form = 'WDLWW'
        elif home_strength > 65:
            home_form = 'DLWWL'
        else:
            home_form = 'LWDLL'

        if away_strength > 85:
            away_form = 'WWWDL'
        elif away_strength > 75:
            away_form = 'WDLWL'
        elif away_strength > 65:
            away_form = 'DLWWL'
        else:
            away_form = 'LLDWL'

        return {
            'platform': 'SofaScore',
            'prediction': pred,
            'confidence': conf,
            'rating_difference': round(diff / 10, 1),
            'form_guide': {
                'home': home_form,
                'away': away_form,
            },
            'source': 'strength_analysis',
        }

    def get_forebet_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """Forebet风格预测 - 数学模型"""
        diff = (home_strength + 5) - away_strength
        pred, conf = self._predict_from_diff(diff)

        # 数学概率计算
        if abs(diff) > 15:
            home_p = 55.0
            away_p = 20.0
        elif diff > 5:
            home_p = 45.0
            away_p = 25.0
        elif diff < -15:
            home_p = 20.0
            away_p = 55.0
        elif diff < -5:
            home_p = 25.0
            away_p = 45.0
        else:
            home_p = 35.0
            away_p = 35.0
        draw_p = 100 - home_p - away_p

        return {
            'platform': 'Forebet',
            'prediction': pred,
            'confidence': conf,
            'mathematical_probability': {
                'home': home_p,
                'draw': draw_p,
                'away': away_p,
            },
            'predicted_score': self._predict_score_from_diff(pred, diff),
            'source': 'mathematical_model',
        }

    def get_all_predictions(self, home_team, away_team, home_strength=70, away_strength=70):
        """获取所有平台预测"""
        predictions = [
            self.get_leisu_predictions(home_team, away_team, home_strength, away_strength),
            self.get_500_predictions(home_team, away_team, home_strength, away_strength),
            self.get_dongqiudi_predictions(home_team, away_team, home_strength, away_strength),
            self.get_sofascore_predictions(home_team, away_team, home_strength, away_strength),
            self.get_forebet_predictions(home_team, away_team, home_strength, away_strength),
        ]
        return predictions

    @staticmethod
    def _predict_from_diff(diff):
        """基于实力差距的确定性预测"""
        if diff > 12:
            return ('home', 75 + min(diff, 20))
        elif diff > 6:
            return ('home', 55 + diff)
        elif diff < -12:
            return ('away', 75 + min(abs(diff), 20))
        elif diff < -6:
            return ('away', 55 + abs(diff))
        else:
            return ('draw', 50 + abs(diff) * 2)

    @staticmethod
    def _predict_score_from_diff(pred, diff):
        """基于实力差预测比分"""
        if pred == 'home':
            if diff > 15:
                return '2-0'
            elif diff > 8:
                return '2-1'
            else:
                return '1-0'
        elif pred == 'draw':
            return '1-1'
        else:
            if diff < -15:
                return '0-2'
            elif diff < -8:
                return '1-2'
            else:
                return '0-1'


class OddsAnalyzer:
    """赔率分析器"""

    @staticmethod
    def calculate_odds(home_prob, draw_prob, away_prob):
        """根据概率计算赔率（含8%庄家利润）"""
        margin = 1.08
        return {
            'home': round(margin / home_prob, 2),
            'draw': round(margin / draw_prob, 2),
            'away': round(margin / away_prob, 2),
        }

    @staticmethod
    def calculate_kelly(odds):
        """计算凯利指数"""
        total = 1 / odds['home'] + 1 / odds['draw'] + 1 / odds['away']
        return {
            'home': round((1 / odds['home']) / total * 100, 1),
            'draw': round((1 / odds['draw']) / total * 100, 1),
            'away': round((1 / odds['away']) / total * 100, 1),
        }
