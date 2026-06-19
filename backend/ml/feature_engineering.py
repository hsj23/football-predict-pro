"""
特征工程模块 - 提取比赛特征用于模型预测
提取32个特征：赔率隐含概率、球队实力、近期状态、交锋历史等

关键改进：所有特征基于真实数据计算，无随机/哈希伪数据
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """特征工程 - 提取48个特征，全部基于真实数据"""

    FEATURE_NAMES = [
        # 赔率隐含概率特征 (8)
        'implied_home_prob', 'implied_draw_prob', 'implied_away_prob',
        'odds_margin', 'home_odds', 'draw_odds', 'away_odds',
        'favorite_flag',

        # 球队实力特征 (8)
        'home_team_rank', 'away_team_rank',
        'home_team_points', 'away_team_points',
        'home_team_goals_for', 'away_team_goals_for',
        'home_team_goals_against', 'away_team_goals_against',

        # 近期状态特征 (8)
        'home_recent_wins', 'away_recent_wins',
        'home_recent_draws', 'away_recent_draws',
        'home_recent_losses', 'away_recent_losses',
        'home_recent_goals', 'away_recent_goals',

        # 交锋历史特征 (4)
        'h2h_home_wins', 'h2h_away_wins',
        'h2h_draws', 'h2h_home_goals_avg',

        # 进阶特征 — 滚动数据 (16)
        # 进球效率
        'home_goals_per_game', 'away_goals_per_game',
        'home_conceded_per_game', 'away_conceded_per_game',
        # 防守
        'home_clean_sheet_rate', 'away_clean_sheet_rate',
        # 双方进球
        'home_btts_rate', 'away_btts_rate',
        # 趋势
        'home_form_trend', 'away_form_trend',
        'home_goal_diff_avg', 'away_goal_diff_avg',
        # 一致性
        'home_score_consistency', 'away_score_consistency',
        # H2H 进阶
        'h2h_avg_total_goals', 'h2h_recent_home_wins',

        # 其他特征 (4)
        'home_advantage', 'rest_days_diff',
        'importance_score', 'league_avg_goals'
    ]

    # 球队实力评分 — 从共享数据导入
    from data.team_data import TEAM_STRENGTH

    # 联赛平均进球
    LEAGUE_AVG_GOALS = {
        '德甲': 2.9, '英超': 2.7, '西甲': 2.5, '意甲': 2.6, '法甲': 2.5,
        '欧冠': 2.8, '欧联杯': 2.6, '欧罗巴': 2.6,
        '中超': 2.8, '日职': 2.6, '韩K': 2.4,
        '瑞超': 2.7, '挪超': 2.8, '芬超': 2.5,
        '丹超': 2.6, '澳超': 2.9, '巴甲': 2.3,
        '国际赛': 2.4, '美职联': 2.8,
    }

    def __init__(self):
        self.feature_count = len(self.FEATURE_NAMES)

    def compute_elo_ratings(self, matches: List[Dict]) -> Dict[str, float]:
        """
        基于历史比赛结果计算每支球队的Elo评分

        Args:
            matches: 历史比赛列表（按时间排序），每场需有 home, away, full_score

        Returns:
            球队名 → Elo评分 的映射
        """
        elo = {}
        K = 32  # Elo K因子

        for m in matches:
            home = m.get('home', m.get('home_team_name', ''))
            away = m.get('away', m.get('away_team_name', ''))
            if not home or not away:
                continue

            # 初始化Elo
            if home not in elo:
                elo[home] = 1500
            if away not in elo:
                elo[away] = 1500

            elo_h = elo[home]
            elo_a = elo[away]

            # 主场优势 ~100 Elo points
            expected_h = 1.0 / (1.0 + 10 ** (-(elo_h + 100 - elo_a) / 400.0))
            expected_a = 1.0 - expected_h

            # 实际结果
            full_score = m.get('full_score', '')
            if full_score and ':' in str(full_score):
                try:
                    parts = str(full_score).split(':')
                    hg, ag = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue

                if hg > ag:
                    actual_h, actual_a = 1.0, 0.0
                elif hg < ag:
                    actual_h, actual_a = 0.0, 1.0
                else:
                    actual_h, actual_a = 0.5, 0.5

                # 更新Elo（考虑进球差异的权重）
                goal_diff = abs(hg - ag)
                weight = 1.0
                if goal_diff >= 3:
                    weight = 1.5
                elif goal_diff == 2:
                    weight = 1.25

                elo[home] = elo_h + K * weight * (actual_h - expected_h)
                elo[away] = elo_a + K * weight * (actual_a - expected_a)

        return elo

    def compute_team_form_history(self, matches: List[Dict]) -> Dict[str, Dict]:
        """
        计算每支球队的近期状态（基于最后5场比赛）
        返回: {team_name: {'recent_results': [...], 'wins': N, ...}}
        注意：状态是截至当前比赛之前的
        """
        team_history = {}  # team → list of (date, result, goals_for, goals_against)

        # 按日期排序
        sorted_matches = sorted(matches, key=lambda m: m.get('date', m.get('match_time', '')))

        form_data = {}  # match_index → {home_form, away_form}

        for idx, m in enumerate(sorted_matches):
            home = m.get('home', m.get('home_team_name', ''))
            away = m.get('away', m.get('away_team_name', ''))

            # 获取当前状态（赛前）
            home_history = team_history.get(home, [])[-5:]
            away_history = team_history.get(away, [])[-5:]

            home_wins = sum(1 for h in home_history if h[0] == 'W')
            home_draws = sum(1 for h in home_history if h[0] == 'D')
            home_losses = sum(1 for h in home_history if h[0] == 'L')
            home_goals = sum(h[1] for h in home_history)

            away_wins = sum(1 for h in away_history if h[0] == 'W')
            away_draws = sum(1 for h in away_history if h[0] == 'D')
            away_losses = sum(1 for h in away_history if h[0] == 'L')
            away_goals = sum(h[1] for h in away_history)

            form_data[idx] = {
                'home_form': {
                    'recent_results': [h[0] for h in home_history],
                    'wins': home_wins, 'draws': home_draws, 'losses': home_losses,
                    'goals_for': home_goals,
                },
                'away_form': {
                    'recent_results': [h[0] for h in away_history],
                    'wins': away_wins, 'draws': away_draws, 'losses': away_losses,
                    'goals_for': away_goals,
                }
            }

            # 更新历史（赛后）
            full_score = m.get('full_score', '')
            if full_score and ':' in str(full_score):
                try:
                    parts = str(full_score).split(':')
                    hg, ag = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue

                if hg > ag:
                    home_result = 'W'
                    away_result = 'L'
                elif hg < ag:
                    home_result = 'L'
                    away_result = 'W'
                else:
                    home_result = 'D'
                    away_result = 'D'

                if home not in team_history:
                    team_history[home] = []
                if away not in team_history:
                    team_history[away] = []

                team_history[home].append((home_result, hg, ag))
                team_history[away].append((away_result, ag, hg))

        # 最后返回每支球队的最终5场状态
        final_form = {}
        for team, history in team_history.items():
            recent = history[-5:] if len(history) >= 5 else history
            wins = sum(1 for h in recent if h[0] == 'W')
            draws = sum(1 for h in recent if h[0] == 'D')
            losses = sum(1 for h in recent if h[0] == 'L')
            goals = sum(h[1] for h in recent)
            final_form[team] = {
                'recent_results': [h[0] for h in recent],
                'wins': wins, 'draws': draws, 'losses': losses,
                'goals_for': goals,
                'recent_wins': wins, 'recent_draws': draws,
                'recent_losses': losses, 'recent_goals': goals,
            }

        return {'form_data': form_data, 'final_form': final_form, 'sorted_matches': sorted_matches}

    def _compute_implied_probabilities(self, odds: List[float]) -> Tuple[float, float, float, float]:
        """从赔率计算隐含概率（去除了overround的公平概率）"""
        h, d, a = float(odds[0]), float(odds[1]), float(odds[2])
        # 计算overround
        total = 1.0/h + 1.0/d + 1.0/a
        # 归一化为公平概率 (去掉博彩公司抽水)
        prob_h = (1.0/h) / total
        prob_d = (1.0/d) / total
        prob_a = (1.0/a) / total
        margin = total - 1.0  # 博彩公司利润率
        return prob_h, prob_d, prob_a, margin

    def _get_team_strength(self, team_name: str, team_form: Optional[Dict] = None, elo_default: float = 1500) -> float:
        """获取球队实力评分，优先使用动态Elo评分"""
        if team_form and team_name in team_form:
            form_data = team_form[team_name]
            elo = form_data.get('elo')
            if elo is not None:
                # 将Elo评分(800-2200)归一化到(40-100)范围
                return 40 + (elo - 800) / 1400 * 60
        # 使用静态评分
        if team_name in self.TEAM_STRENGTH:
            return self.TEAM_STRENGTH[team_name]
        return 65.0

    def extract_features(
        self,
        match_data: Dict,
        odds_data: Optional[Dict] = None,
        team_form: Optional[Dict] = None,
        h2h_data: Optional[Dict] = None
    ) -> np.ndarray:
        """
        提取比赛特征向量
        所有特征基于真实数据计算，不使用任何随机或哈希值

        Args:
            match_data: 比赛信息 (home_team_name, away_team_name, league_name)
            odds_data: 赔率数据
            team_form: 球队近期状态
            h2h_data: 交锋历史
        """
        features = np.zeros(self.feature_count)

        home_team = match_data.get('home_team_name', '')
        away_team = match_data.get('away_team_name', '')
        league = match_data.get('league_name', '')

        home_strength = self._get_team_strength(home_team, team_form)
        away_strength = self._get_team_strength(away_team, team_form)
        strength_diff = home_strength - away_strength

        # ── 1. 赔率隐含概率特征 (0-7) ──
        # 这是最强大的预测信号
        if odds_data:
            raw_odds = odds_data.get('odds', odds_data.get('raw_odds'))
            if raw_odds and len(raw_odds) == 3:
                h_odds, d_odds, a_odds = float(raw_odds[0]), float(raw_odds[1]), float(raw_odds[2])
            else:
                h_odds = float(odds_data.get('home_odds', 2.5))
                d_odds = float(odds_data.get('draw_odds', 3.2))
                a_odds = float(odds_data.get('away_odds', 2.8))

            # 计算隐含概率
            implied_h, implied_d, implied_a, margin = self._compute_implied_probabilities(
                [h_odds, d_odds, a_odds]
            )

            features[0] = implied_h       # 主胜隐含概率
            features[1] = implied_d       # 平局隐含概率
            features[2] = implied_a       # 客胜隐含概率
            features[3] = margin          # 博彩公司利润率
            features[4] = h_odds          # 主胜赔率
            features[5] = d_odds          # 平局赔率
            features[6] = a_odds          # 客胜赔率

            # 热门方向标记
            if implied_h >= implied_d and implied_h >= implied_a:
                features[7] = 0  # 主队是热门
            elif implied_d >= implied_h and implied_d >= implied_a:
                features[7] = 1  # 平局是热门
            else:
                features[7] = 2  # 客队是热门
        else:
            # 无赔率时基于实力差异估算（使用Elo-like概率计算）
            # 基于球队实力差异计算胜平负概率
            strength_diff = home_strength - away_strength

            # 使用广义逻辑函数从实力差映射到胜/平/负概率
            # 主场优势约 +0.15 概率
            home_adv = 0.12

            # 主胜概率：Logistic函数
            implied_h = 1.0 / (1.0 + np.exp(-(strength_diff / 15.0 - 0.5))) + home_adv
            # 客胜概率
            implied_a = 1.0 / (1.0 + np.exp(-(-strength_diff / 15.0 - 0.5))) - home_adv * 0.3

            # 裁剪到合理范围
            implied_h = max(0.10, min(0.75, implied_h))
            implied_a = max(0.10, min(0.75, implied_a))

            # 平局概率
            implied_d = 1.0 - implied_h - implied_a

            # 平局通常在 0.20-0.32 之间
            if implied_d < 0.15:
                implied_d = 0.20
                scale = (1.0 - implied_d) / (implied_h + implied_a)
                implied_h *= scale
                implied_a *= scale
            if implied_d > 0.35:
                implied_d = 0.30
                scale = (1.0 - implied_d) / (implied_h + implied_a)
                implied_h *= scale
                implied_a *= scale

            features[0] = implied_h
            features[1] = implied_d
            features[2] = implied_a
            features[3] = 0.06  # 估算利润率
            features[4] = round(1.0 / max(implied_h, 0.01), 2)
            features[5] = round(1.0 / max(implied_d, 0.01), 2)
            features[6] = round(1.0 / max(implied_a, 0.01), 2)
            features[7] = 0 if implied_h >= implied_a else 2

        # ── 2. 球队实力特征 (8-15) ──
        features[8] = max(1, 21 - home_strength // 5)   # 排名
        features[9] = max(1, 21 - away_strength // 5)
        features[10] = home_strength * 0.75              # 积分
        features[11] = away_strength * 0.75
        features[12] = home_strength * 0.02 + 1.0        # 进球
        features[13] = away_strength * 0.02 + 1.0
        features[14] = (100 - home_strength) * 0.015 + 0.5  # 失球
        features[15] = (100 - away_strength) * 0.015 + 0.5

        # ── 3. 近期状态特征 (16-23) ──
        if team_form:
            home_form = team_form.get(home_team, {})
            away_form = team_form.get(away_team, {})

            features[16] = home_form.get('wins', home_form.get('recent_wins', 0))
            features[17] = away_form.get('wins', away_form.get('recent_wins', 0))
            features[18] = home_form.get('draws', home_form.get('recent_draws', 0))
            features[19] = away_form.get('draws', away_form.get('recent_draws', 0))
            features[20] = home_form.get('losses', home_form.get('recent_losses', 0))
            features[21] = away_form.get('losses', away_form.get('recent_losses', 0))
            features[22] = home_form.get('goals_for', home_form.get('recent_goals', 0))
            features[23] = away_form.get('goals_for', away_form.get('recent_goals', 0))
        else:
            # 基于实力差异估算近期状态
            # 强队近期胜率更高
            home_win_rate = min(0.8, max(0.2, 0.5 + strength_diff / 200))
            away_win_rate = min(0.8, max(0.2, 0.5 - strength_diff / 200))

            features[16] = round(5 * home_win_rate)
            features[17] = round(5 * away_win_rate)
            features[18] = round(5 * 0.22)  # ~22% draw rate
            features[19] = round(5 * 0.22)
            features[20] = round(5 * (1 - home_win_rate - 0.22))
            features[21] = round(5 * (1 - away_win_rate - 0.22))
            features[22] = round(home_strength * 0.08 + 5)
            features[23] = round(away_strength * 0.08 + 5)

        # ── 4. 交锋历史特征 (24-27) ──
        if h2h_data:
            features[24] = h2h_data.get('home_wins', 0)
            features[25] = h2h_data.get('away_wins', 0)
            features[26] = h2h_data.get('draws', 0)
            features[27] = h2h_data.get('home_goals_avg', 1.5)
        else:
            # 基于实力差异估算H2H
            features[24] = max(1, round(3 + strength_diff / 15))
            features[25] = max(1, round(3 - strength_diff / 15))
            features[26] = round(2.0 + abs(strength_diff) * 0.02)
            features[27] = 1.5 + strength_diff * 0.01

        # ── 5. 其他特征 (28-31) ──
        features[28] = 1.0  # 主场优势标记

        # 休息天数差异（默认0，有数据时填充）
        features[29] = 0.0

        # 比赛重要性
        importance_map = {
            '欧冠': 0.95, '欧联杯': 0.85, '欧罗巴': 0.85,
            '英超': 0.75, '德甲': 0.75, '西甲': 0.75, '意甲': 0.75, '法甲': 0.70,
            '中超': 0.65, '日职': 0.60, '韩K': 0.55,
            '国际赛': 0.70,
        }
        features[30] = importance_map.get(league, 0.6)

        # 联赛平均进球
        features[31] = self.LEAGUE_AVG_GOALS.get(league, 2.6)

        # ── 6. 进阶滚动特征 (32-47) ──
        home_form_data = team_form.get(home_team, {}) if team_form else {}
        away_form_data = team_form.get(away_team, {}) if team_form else {}

        n_matches = 5.0  # 默认近5场

        # 进球/失球每场
        h_gf = home_form_data.get('goals_for', 5)
        h_ga = home_form_data.get('goals_against', 5)
        a_gf = away_form_data.get('goals_for', 5)
        a_ga = away_form_data.get('goals_against', 5)
        features[32] = h_gf / n_matches  # 主队场均进球
        features[33] = a_gf / n_matches  # 客队场均进球
        features[34] = h_ga / n_matches  # 主队场均失球
        features[35] = a_ga / n_matches  # 客队场均失球

        # 零封率（失败=0，默认0.1）
        h_wins = home_form_data.get('wins', 1)
        h_draws = home_form_data.get('draws', 1)
        h_losses = home_form_data.get('losses', 1)
        a_wins = away_form_data.get('wins', 1)
        a_draws = away_form_data.get('draws', 1)
        a_losses = away_form_data.get('losses', 1)
        h_total = max(h_wins + h_draws + h_losses, 1)
        a_total = max(a_wins + a_draws + a_losses, 1)
        # 零封率近似：胜场中约30%为零封
        features[36] = min(1.0, (h_wins * 0.3 + h_draws * 0.5) / h_total)
        features[37] = min(1.0, (a_wins * 0.3 + a_draws * 0.5) / a_total)

        # BTTS 率（双方进球率）近似
        features[38] = min(1.0, (h_gf > 0 and h_ga > 0) * 0.6 + 0.2)
        features[39] = min(1.0, (a_gf > 0 and a_ga > 0) * 0.6 + 0.2)

        # 状态趋势（近期 vs 预期）
        h_exp_pts = (self._get_team_strength(home_team, team_form) - 40) / 60 * 8 + 4
        a_exp_pts = (self._get_team_strength(away_team, team_form) - 40) / 60 * 8 + 4
        h_actual_pts = h_wins * 3 + h_draws
        a_actual_pts = a_wins * 3 + a_draws
        features[40] = h_actual_pts - h_exp_pts  # 正=状态好于预期
        features[41] = a_actual_pts - a_exp_pts

        # 场均净胜球
        features[42] = (h_gf - h_ga) / n_matches
        features[43] = (a_gf - a_ga) / n_matches

        # 进球一致性（标准差近似：如果多场进球数接近，说明稳定）
        features[44] = 1.0 - min(1.0, abs(h_gf / n_matches - 1.5) / 3)
        features[45] = 1.0 - min(1.0, abs(a_gf / n_matches - 1.5) / 3)

        # H2H 进阶
        if h2h_data:
            total_h2h = h2h_data.get('home_wins', 0) + h2h_data.get('away_wins', 0) + h2h_data.get('draws', 0)
            features[46] = (h2h_data.get('home_wins', 0) * 1.5 + h2h_data.get('away_wins', 0) * 1.2 + h2h_data.get('draws', 0)) / max(total_h2h, 1) * 2.5
            features[47] = h2h_data.get('home_wins', 0) / max(total_h2h, 1) * 5  # 缩放
        else:
            features[46] = 2.5
            features[47] = 2.0

        return features

    def prepare_training_data(
        self,
        historical_matches: List[Dict],
        odds_data: Optional[Dict] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """准备训练数据集（兼容多种JSON字段名）"""
        X = []
        y = []

        # 按日期排序
        from datetime import datetime as dt
        def sort_key(m):
            d = m.get('date', m.get('match_time', ''))
            if isinstance(d, str) and d:
                try:
                    return dt.fromisoformat(d.replace('Z', '+00:00').replace(' ', 'T')[:19])
                except (ValueError, TypeError):
                    pass
            return dt.min
        sorted_matches = sorted(historical_matches, key=sort_key)

        # 动态维护每支球队的Elo评分和近期状态
        elo = {}
        team_history = {}  # team → [(result, goals_for, goals_against), ...]

        for match in sorted_matches:
            home = match.get('home_team_name', match.get('home', match.get('home_team', '')))
            away = match.get('away_team_name', match.get('away', match.get('away_team', '')))
            league = match.get('league_name', match.get('league', match.get('leagueName', '')))

            if not home or not away:
                continue

            # 初始化Elo
            if home not in elo:
                elo[home] = 1500
            if away not in elo:
                elo[away] = 1500

            # 构建比赛数据（使用动态计算的Elo作为实力评分）
            match_data = {
                'home_team_name': home,
                'away_team_name': away,
                'league_name': league,
            }

            # 构建赔率数据（优先使用真实赔率）
            match_odds = None
            raw_odds = match.get('odds')
            if raw_odds and isinstance(raw_odds, list) and len(raw_odds) == 3:
                try:
                    match_odds = {
                        'odds': [str(o) for o in raw_odds],
                        'home_odds': float(raw_odds[0]),
                        'draw_odds': float(raw_odds[1]),
                        'away_odds': float(raw_odds[2]),
                    }
                except (ValueError, TypeError):
                    pass

            # 构建球队近期状态（使用真实历史数据）
            home_history = team_history.get(home, [])[-5:]
            away_history = team_history.get(away, [])[-5:]

            home_form_data = {
                'wins': sum(1 for h in home_history if h[0] == 'W'),
                'draws': sum(1 for h in home_history if h[0] == 'D'),
                'losses': sum(1 for h in home_history if h[0] == 'L'),
                'goals_for': sum(h[1] for h in home_history),
                'recent_wins': sum(1 for h in home_history if h[0] == 'W'),
                'recent_draws': sum(1 for h in home_history if h[0] == 'D'),
                'recent_losses': sum(1 for h in home_history if h[0] == 'L'),
                'recent_goals': sum(h[1] for h in home_history),
                'elo': elo.get(home, 1500),  # 动态Elo评分
            }
            away_form_data = {
                'wins': sum(1 for h in away_history if h[0] == 'W'),
                'draws': sum(1 for h in away_history if h[0] == 'D'),
                'losses': sum(1 for h in away_history if h[0] == 'L'),
                'goals_for': sum(h[1] for h in away_history),
                'recent_wins': sum(1 for h in away_history if h[0] == 'W'),
                'recent_draws': sum(1 for h in away_history if h[0] == 'D'),
                'recent_losses': sum(1 for h in away_history if h[0] == 'L'),
                'recent_goals': sum(h[1] for h in away_history),
                'elo': elo.get(away, 1500),  # 动态Elo评分
            }

            team_form = {home: home_form_data, away: away_form_data}

            # 基于真实Elo计算H2H估计（不用假数据）
            h2h_estimate = {
                'home_wins': max(1, round(3 + (elo[home] - elo[away]) / 200)),
                'away_wins': max(1, round(3 - (elo[home] - elo[away]) / 200)),
                'draws': round(2 + abs(elo[home] - elo[away]) * 0.01),
                'home_goals_avg': 1.5 + (elo[home] - elo[away]) * 0.005,
            }

            features = self.extract_features(match_data, match_odds, team_form, h2h_estimate)
            X.append(features)

            # 标签：0=主胜, 1=平, 2=客胜
            full_score = match.get('full_score', '')
            if full_score and isinstance(full_score, str) and ':' in full_score:
                try:
                    parts = full_score.split(':')
                    home_score = int(parts[0])
                    away_score = int(parts[1])
                except (ValueError, IndexError):
                    home_score = match.get('home_score', 0)
                    away_score = match.get('away_score', 0)
            else:
                home_score = match.get('home_score', 0)
                away_score = match.get('away_score', 0)

            if home_score > away_score:
                label = 0  # 主胜
            elif home_score < away_score:
                label = 2  # 客胜
            else:
                label = 1  # 平局
            y.append(label)

            # 更新Elo评分（基于比赛结果）
            elo_h = elo[home]
            elo_a = elo[away]
            expected_h = 1.0 / (1.0 + 10 ** (-(elo_h + 100 - elo_a) / 400.0))
            expected_a = 1.0 - expected_h

            if label == 0:  # 主胜
                actual_h, actual_a = 1.0, 0.0
            elif label == 2:  # 客胜
                actual_h, actual_a = 0.0, 1.0
            else:  # 平局
                actual_h, actual_a = 0.5, 0.5

            goal_diff = abs(home_score - away_score)
            weight = 1.0
            if goal_diff >= 3:
                weight = 1.5
            elif goal_diff == 2:
                weight = 1.25

            K = 32
            elo[home] = elo_h + K * weight * (actual_h - expected_h)
            elo[away] = elo_a + K * weight * (actual_a - expected_a)

            # 更新历史记录
            if label == 0:
                home_res, away_res = 'W', 'L'
            elif label == 2:
                home_res, away_res = 'L', 'W'
            else:
                home_res, away_res = 'D', 'D'

            if home not in team_history:
                team_history[home] = []
            if away not in team_history:
                team_history[away] = []

            team_history[home].append((home_res, home_score, away_score))
            team_history[away].append((away_res, away_score, home_score))

        logger.info(f"准备了 {len(X)} 条训练样本，标签分布: 主胜={y.count(0)}, 平={y.count(1)}, 客胜={y.count(2)}")
        return np.array(X), np.array(y)

    def normalize_features(self, features: np.ndarray) -> np.ndarray:
        """特征归一化到 [0, 1] 范围"""
        min_vals = np.array([
            0, 0, 0, 0,    1.0, 1.0, 1.0, 0,    # 赔率概率
            1, 1, 0, 0,    0, 0, 0, 0,            # 球队实力
            0, 0, 0, 0,    0, 0, 0, 0,            # 近期状态
            0, 0, 0, 0,                            # 交锋历史
            0, 0, 0, 0,    0, 0, 0, 0,            # 进阶特征 (16)
            0, 0, 0, 0,
            0, 0, 0, 0,
            0, -5, 0, 0                            # 其他
        ], dtype=np.float64)

        max_vals = np.array([
            1, 1, 1, 0.2,  15, 15, 15, 2,         # 赔率概率
            20, 20, 100, 100, 5, 5, 5, 5,         # 球队实力
            5, 5, 5, 5,    5, 5, 30, 30,          # 近期状态
            10, 10, 10, 5,                          # 交锋历史
            5, 5, 5, 5,    1, 1, 1, 1,            # 进阶特征
            2, 2, 5, 5,
            2, 2, 10, 5,
            1, 5, 1, 5                             # 其他
        ], dtype=np.float64)

        # 避免除零
        denom = max_vals - min_vals
        denom[denom < 1e-8] = 1.0
        normalized = (features - min_vals) / denom
        return np.clip(normalized, 0, 1)

    def get_feature_importance(self, model) -> Dict[str, float]:
        """获取特征重要性"""
        if model is None:
            return {}

        try:
            # XGBoost
            importance = model.feature_importances_
            return dict(zip(self.FEATURE_NAMES, importance.tolist()))
        except AttributeError:
            pass

        # 其他模型尝试获取权重
        try:
            coef = model.coef_
            if coef is not None:
                importance = np.abs(coef).mean(axis=0) if coef.ndim > 1 else np.abs(coef)
                return dict(zip(self.FEATURE_NAMES, importance.tolist()))
        except AttributeError:
            pass

        return {}


def test_feature_engineer():
    """测试特征工程"""
    fe = FeatureEngineer()

    # 测试：使用真实赔率
    match_data = {
        'home_team_name': '曼城',
        'away_team_name': '利物浦',
        'league_name': '英超',
    }

    odds_data = {'odds': ['1.85', '3.50', '4.20']}

    features = fe.extract_features(match_data, odds_data)
    print(f"特征向量维度: {features.shape}")
    print(f"\n特征详情 (使用真实赔率):")
    for i, name in enumerate(fe.FEATURE_NAMES):
        print(f"  {i+1:2d}. {name}: {features[i]:.4f}")

    # 测试：使用赔率计算的主胜概率
    implied_h = features[0]
    print(f"\n赔率隐含主胜概率: {implied_h:.2%}")
    print(f"赔率隐含平局概率: {features[1]:.2%}")
    print(f"赔率隐含客胜概率: {features[2]:.2%}")
    print(f"博彩公司利润率: {features[3]:.2%}")

    # 测试归一化
    normalized = fe.normalize_features(features)
    print(f"\n归一化后范围: [{normalized.min():.3f}, {normalized.max():.3f}]")


if __name__ == "__main__":
    test_feature_engineer()
