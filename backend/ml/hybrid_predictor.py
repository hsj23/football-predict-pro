"""
混合预测器 - 综合赔率、ML模型、外部预测的最佳准确率
策略:
  1. 有赔率时: 赔率隐含概率(55%) + ML模型(30%) + 外部共识(15%)
  2. 无赔率时: ML模型(70%) + 外部共识(30%)
  3. 实力接近时: 提高平局概率, 增加外部共识权重
"""
import json
import os
import sys
import logging
import hashlib
import numpy as np
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.feature_engineering import FeatureEngineer
from ml.model_trainer import ModelTrainer

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')

RESULT_NAMES = {0: 'home', 1: 'draw', 2: 'away'}
RESULT_CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}


class HybridPredictor:
    """混合预测器 - 多信号融合, 针对实力接近比赛优化"""

    # 类级别缓存（所有实例共享）
    _team_form_cache = None   # team_name -> {wins, draws, losses, goals_for, goals_against}
    _h2h_cache = None         # (home, away) -> {home_wins, away_wins, draws, home_goals_avg}
    _ensemble = None          # 集成模型（CatBoost + XGBoost + LightGBM）
    _dc_model = None          # Dixon-Coles 进球模型

    def __init__(self):
        self.fe = FeatureEngineer()
        self.trainer = ModelTrainer()
        self.model_loaded = False
        self.elo_ratings = {}  # 动态Elo评分
        self.ensemble = None   # 集成模型
        self.dc_model = None   # Dixon-Coles 进球模型

        # 加载已训练的模型
        model_path = os.path.join(os.path.dirname(__file__), 'models', 'xgboost_model.pkl')
        if os.path.exists(model_path):
            try:
                self.trainer.load_model(model_path)
                self.model_loaded = True
                logger.info("已加载预训练模型")
            except Exception as e:
                logger.warning(f"加载模型失败: {e}")

        # 从训练数据计算Elo评分
        self._load_elo_ratings()
        # 加载真实form/H2H数据
        self._load_real_form_cache()
        # 加载集成模型（CatBoost 等）
        self._load_ensemble_model()
        # 初始化 Dixon-Coles（延迟加载，首次预测时才拟合）

    def _load_real_form_cache(self):
        """从 training_data.json 构建 form 和 H2H 缓存"""
        if HybridPredictor._team_form_cache is not None:
            return

        training_file = os.path.join(DATA_DIR, 'training_data.json')
        if not os.path.exists(training_file):
            return

        try:
            with open(training_file, 'r', encoding='utf-8') as f:
                matches = json.load(f)

            # 收集每支队伍的比赛记录
            team_records = {}  # team -> [(date, scored, conceded), ...]
            h2h_records = {}   # (home, away) -> [(home_score, away_score), ...]

            for m in matches:
                home = m.get('home', '').strip()
                away = m.get('away', '').strip()
                hs = m.get('home_score')
                ags = m.get('away_score')
                date = m.get('date', '')
                if not home or not away or hs is None or ags is None:
                    continue
                hs, ags = int(hs), int(ags)

                team_records.setdefault(home, []).append((date, hs, ags))
                team_records.setdefault(away, []).append((date, ags, hs))
                h2h_records.setdefault((home, away), []).append((hs, ags))

            # 按日期降序排列
            for t in team_records:
                team_records[t].sort(key=lambda x: x[0], reverse=True)

            # 构建 form 缓存：取每队最近 10 场
            form_cache = {}
            for team, records in team_records.items():
                recent = records[:10]
                if not recent:
                    continue
                wins = sum(1 for _, s, c in recent if s > c)
                draws = sum(1 for _, s, c in recent if s == c)
                losses = sum(1 for _, s, c in recent if s < c)
                goals_for = sum(s for _, s, c in recent)
                goals_against = sum(c for _, s, c in recent)
                form_cache[team] = {
                    'wins': wins, 'draws': draws, 'losses': losses,
                    'goals_for': goals_for, 'goals_against': goals_against,
                }

            # 构建 H2H 缓存
            h2h_cache = {}
            for (home, away), scores in h2h_records.items():
                if len(scores) < 1:
                    continue
                hw = sum(1 for hs, ags in scores if hs > ags)
                aw = sum(1 for hs, ags in scores if ags > hs)
                dw = sum(1 for hs, ags in scores if hs == ags)
                home_goals = sum(hs for hs, ags in scores)
                h2h_cache[(home, away)] = {
                    'home_wins': hw, 'away_wins': aw, 'draws': dw,
                    'home_goals_avg': round(home_goals / len(scores), 2) if scores else 1.5,
                }

            HybridPredictor._team_form_cache = form_cache
            HybridPredictor._h2h_cache = h2h_cache
            logger.info(f"已加载 {len(form_cache)} 队 form 数据, {len(h2h_cache)} 对 H2H 数据")
        except Exception as e:
            logger.warning(f"加载真实 form/H2H 缓存失败: {e}")

    def _load_ensemble_model(self):
        """加载集成模型（CatBoost + XGBoost + LightGBM），类级别缓存"""
        if HybridPredictor._ensemble is not None:
            self.ensemble = HybridPredictor._ensemble
            return
        try:
            from ml.ensemble_trainer import EnsemblePredictor
            HybridPredictor._ensemble = EnsemblePredictor()
            if HybridPredictor._ensemble.model_loaded:
                logger.info("已加载集成模型（类缓存）")
            else:
                HybridPredictor._ensemble = None
        except Exception as e:
            logger.warning(f"加载集成模型失败: {e}")
            HybridPredictor._ensemble = None
        self.ensemble = HybridPredictor._ensemble

    def _get_dc_prediction(self, home: str, away: str) -> Optional[Dict]:
        """获取 Dixon-Coles 进球预测（含Elo兜底），类级别缓存"""
        try:
            from ml.dixon_coles import DixonColesModel
            if HybridPredictor._dc_model is None:
                HybridPredictor._dc_model = DixonColesModel()
            self.dc_model = HybridPredictor._dc_model
            if self.dc_model and self.dc_model.fitted:
                elo_h = self._get_elo_strength(home)
                elo_a = self._get_elo_strength(away)
                # 标准化到1500基准
                elo_h_raw = self.elo_ratings.get(home, 1500)
                elo_a_raw = self.elo_ratings.get(away, 1500)
                goals = self.dc_model.predict_goals(home, away, elo_h_raw, elo_a_raw)
                rp = goals['result_probs']
                return {
                    'prediction': max(rp, key=rp.get),
                    'prediction_name': {'home':'主胜','draw':'平局','away':'客胜'}[max(rp, key=rp.get)],
                    'confidence': rp[max(rp, key=rp.get)],
                    'probabilities': rp,
                    'predicted_score': goals['most_likely_score'],
                    'expected_goals': goals['expected_goals'],
                    'model': 'dixon_coles',
                }
        except Exception as e:
            logger.debug(f"Dixon-Coles 预测失败: {e}")
        return None

    def _predict_from_ensemble(self, match_data: Dict, odds_data: Optional[Dict] = None,
                               team_form: Optional[Dict] = None, h2h_data: Optional[Dict] = None) -> Optional[Dict]:
        """使用集成模型预测"""
        if self.ensemble is None or not self.ensemble.model_loaded:
            return None
        try:
            features = self.fe.extract_features(match_data, odds_data, team_form, h2h_data)
            probs = self.ensemble.predict_proba(features)
            pred_idx = int(np.argmax(probs))
            return {
                'prediction': RESULT_NAMES[pred_idx],
                'prediction_name': RESULT_CN[RESULT_NAMES[pred_idx]],
                'confidence': round(float(max(probs)) * 100, 1),
                'probabilities': {
                    'home': round(float(probs[0]) * 100, 1),
                    'draw': round(float(probs[1]) * 100, 1),
                    'away': round(float(probs[2]) * 100, 1),
                }
            }
        except Exception as e:
            logger.debug(f"集成模型预测失败: {e}")
            return None

    def _load_elo_ratings(self):
        """从训练数据中计算球队Elo评分"""
        training_file = os.path.join(DATA_DIR, 'training_data.json')
        if not os.path.exists(training_file):
            return

        try:
            with open(training_file, 'r', encoding='utf-8') as f:
                matches = json.load(f)

            elo = {}
            for m in matches:
                home = m.get('home', '')
                away = m.get('away', '')
                if not home or not away:
                    continue

                if home not in elo:
                    elo[home] = 1500
                if away not in elo:
                    elo[away] = 1500

                elo_h, elo_a = elo[home], elo[away]
                expected_h = 1.0 / (1.0 + 10 ** (-(elo_h + 100 - elo_a) / 400.0))

                full_score = m.get('full_score', '')
                if not full_score or ':' not in str(full_score):
                    continue
                try:
                    parts = str(full_score).split(':')
                    hg, ag = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue

                if hg > ag:
                    actual_h = 1.0
                elif hg < ag:
                    actual_h = 0.0
                else:
                    actual_h = 0.5

                goal_diff = abs(hg - ag)
                weight = 1.0
                if goal_diff >= 3:
                    weight = 1.5
                elif goal_diff == 2:
                    weight = 1.25

                K = 32
                elo[home] = elo_h + K * weight * (actual_h - expected_h)
                elo[away] = elo_a + K * weight * ((1 - actual_h) - (1 - expected_h))

            self.elo_ratings = elo
            logger.info(f"已加载 {len(elo)} 支球队的Elo评分")

        except Exception as e:
            logger.warning(f"计算Elo评分失败: {e}")
            self.elo_ratings = {}

    def _get_elo_strength(self, team_name: str) -> float:
        """获取球队的Elo-based实力评分 (归一化到 40-100)"""
        if team_name in self.elo_ratings:
            elo = self.elo_ratings[team_name]
            # Elo范围约 800-2200 → 归一化到 40-100
            return round(40 + (elo - 800) / 1400 * 60, 1)
        # 回退到静态评分
        return self.fe._get_team_strength(team_name)

    def _is_close_match(self, home: str, away: str, odds: Optional[List] = None) -> bool:
        """判断是否是实力接近的比赛 — 只在有赔率时才判断"""
        if odds:
            h, d, a = float(odds[0]), float(odds[1]), float(odds[2])
            # 明显一边倒 → 不接近
            if h < 1.50 or a < 1.50:
                return False
            # 赔率接近: 主胜>1.9且客胜<4.5, 或平赔低
            if h > 1.9 and a < 4.5:
                return True
            if d < 3.3:
                return True
            # 赔率差距大 → 不接近
            if h < 1.8 and a > 5.0:
                return False
            if a < 1.8 and h > 5.0:
                return False
            return True

        # 没有赔率时，不判断为接近（避免误判）
        return False

    def _predict_from_odds(self, odds: List) -> Dict:
        """从赔率获取隐含概率预测 — 使用 Shin 方法去除抽水偏差"""
        h, d, a = float(odds[0]), float(odds[1]), float(odds[2])
        probs = self._shin_implied_probs(h, d, a)
        prediction = max(probs, key=probs.get)
        return {
            'prediction': prediction,
            'prediction_name': RESULT_CN[prediction],
            'confidence': probs[prediction],
            'probabilities': probs,
        }

    @staticmethod
    def _shin_implied_probs(h: float, d: float, a: float) -> Dict:
        """
        Shin方法去除博彩公司抽水，获得真实隐含概率

        核心思想：博彩公司为防范内幕交易者，对冷门方设置更高抽水。
        Shin方法通过迭代求解参数 z（内幕交易者比例），
        更准确地还原真实概率，尤其改善平局和客胜的低估问题。

        参考: Shin (1993) "Measuring the Incidence of Insider Trading"
        """
        odds = [h, d, a]
        n = len(odds)
        r = [1.0 / o for o in odds]  # raw implied probs
        r_sum = sum(r)

        # 如果没有抽水（sum ≈ 1），直接归一化
        if abs(r_sum - 1.0) < 0.005:
            return {
                'home': round(r[0] * 100, 1),
                'draw': round(r[1] * 100, 1),
                'away': round(r[2] * 100, 1),
            }

        # 二分搜索 Shin's z 参数
        z_lo, z_hi = 0.0, 0.5
        best_z = 0.0

        for _ in range(50):
            z_mid = (z_lo + z_hi) / 2
            # Shin 公式: p_i = sqrt(z^2 + 4*(1-z)*r_i^2/sum_r) - z / (2*(1-z))
            # 简化: 对于每个 i，计算 adjusted probability
            denom = 2 * (1 - z_mid)
            if denom < 0.0001:
                z_hi = z_mid
                continue

            probs = []
            for ri in r:
                inner = z_mid**2 + 4 * (1 - z_mid) * ri**2
                if inner < 0:
                    inner = 0
                pi = (np.sqrt(inner) - z_mid) / denom
                probs.append(pi)

            p_sum = sum(probs)
            if abs(p_sum - 1.0) < 0.0001:
                best_z = z_mid
                break
            elif p_sum > 1.0:
                z_lo = z_mid
            else:
                z_hi = z_mid
            best_z = z_mid

        # 用最佳 z 计算最终概率
        denom = 2 * (1 - best_z) if (1 - best_z) > 0.0001 else 1.0
        final = []
        for ri in r:
            inner = best_z**2 + 4 * (1 - best_z) * ri**2
            if inner < 0:
                inner = 0
            pi = (np.sqrt(inner) - best_z) / denom
            final.append(max(0.001, pi))

        total = sum(final)
        return {
            'home': round(final[0] / total * 100, 1),
            'draw': round(final[1] / total * 100, 1),
            'away': round(final[2] / total * 100, 1),
        }

    def _predict_from_model(self, match_data: Dict, odds_data: Optional[Dict] = None,
                            team_form: Optional[Dict] = None, h2h_data: Optional[Dict] = None) -> Optional[Dict]:
        """使用ML模型预测"""
        if not self.model_loaded:
            return None

        try:
            features = self.fe.extract_features(match_data, odds_data, team_form, h2h_data)
            features = features.reshape(1, -1)

            if self.trainer.scaler:
                features = self.trainer.scaler.transform(features)

            pred = self.trainer.model.predict(features)[0]
            probs = self.trainer.model.predict_proba(features)[0]

            pred_key = RESULT_NAMES[pred]
            return {
                'prediction': pred_key,
                'prediction_name': RESULT_CN[pred_key],
                'confidence': round(float(max(probs)) * 100, 1),
                'probabilities': {
                    'home': round(float(probs[0]) * 100, 1),
                    'draw': round(float(probs[1]) * 100, 1),
                    'away': round(float(probs[2]) * 100, 1),
                }
            }
        except Exception as e:
            logger.error(f"模型预测失败: {e}")
            return None

    def _get_external_consensus(self, home: str, away: str) -> Optional[Dict]:
        """获取外部预测网站共识"""
        try:
            from services.external_aggregator import get_consensus_prediction
            consensus = get_consensus_prediction(home, away)
            if consensus:
                pred = consensus['prediction']
                total = consensus.get('total_sources', 0)
                if total > 0:
                    return {
                        'prediction': pred,
                        'prediction_name': RESULT_CN.get(pred, pred),
                        'confidence': float(consensus.get('confidence', 50)),
                        'total_sources': total,
                        'home_votes': consensus.get('home_votes', 0),
                        'draw_votes': consensus.get('draw_votes', 0),
                        'away_votes': consensus.get('away_votes', 0),
                    }
        except Exception:
            pass
        return None

    def _elo_based_probs(self, home: str, away: str) -> Dict:
        """基于Elo评分计算胜平负概率"""
        hs = self._get_elo_strength(home)
        aws = self._get_elo_strength(away)
        diff = hs - aws

        # Elo-based probability with home advantage
        # 全球主场胜率约44%，主场优势约+0.15期望进球，对应ELO差约8分
        # 使用较小的主场优势，让模型不过度偏向主胜
        home_adv = 1.5  # 约+2%主场胜率，给平局和客胜留空间
        effective_diff = diff + home_adv

        # Logistic function for home win probability
        home_p = 1.0 / (1.0 + np.exp(-effective_diff / 8.0))

        # Draw probability peaks when teams are equal
        # Max ~28% when diff=0, decreases as diff increases
        draw_p = 0.28 * np.exp(-(effective_diff ** 2) / 200)

        away_p = 1.0 - home_p - draw_p

        # Ensure within reasonable bounds
        home_p = max(0.10, min(0.80, home_p))
        away_p = max(0.10, min(0.80, away_p))
        draw_p = max(0.15, min(0.35, draw_p))

        # Renormalize
        total = home_p + draw_p + away_p
        return {
            'home': round(home_p / total * 100, 1),
            'draw': round(draw_p / total * 100, 1),
            'away': round(away_p / total * 100, 1),
        }

    def _form_based_probs(self, home_form: Dict, away_form: Dict) -> Dict:
        """基于近期真实战绩计算状态概率"""
        hp = home_form.get('wins', 0) * 3 + home_form.get('draws', 0)
        ap = away_form.get('wins', 0) * 3 + away_form.get('draws', 0)
        fd = hp - ap
        hg = home_form.get('goals_for', 0)
        ag = away_form.get('goals_for', 0)
        gd = hg - ag

        # 结合积分差和进球差（基于全球实际分布校准）
        if fd > 5:
            base = {'home': 0.48, 'draw': 0.26, 'away': 0.26}
        elif fd > 1:
            base = {'home': 0.40, 'draw': 0.30, 'away': 0.30}
        elif fd < -5:
            base = {'home': 0.26, 'draw': 0.26, 'away': 0.48}
        elif fd < -1:
            base = {'home': 0.30, 'draw': 0.30, 'away': 0.40}
        else:
            base = {'home': 0.33, 'draw': 0.34, 'away': 0.33}

        # 进球效率修正
        if gd > 3:
            base['home'] += 0.03; base['away'] -= 0.03
        elif gd < -3:
            base['home'] -= 0.03; base['away'] += 0.03

        total = sum(base.values())
        return {k: round(v / total * 100, 1) for k, v in base.items()}

    def predict(
        self,
        home: str,
        away: str,
        league: str = '',
        odds: Optional[List] = None,
        match_id: str = None,
    ) -> Dict:
        """
        综合预测 - 针对实力接近比赛优化

        Args:
            home: 主队名称
            away: 客队名称
            league: 联赛名称
            odds: 赔率列表 [home_odds, draw_odds, away_odds] 或 None
            match_id: 比赛ID，用于查询赔率变化历史
        """
        match_data = {
            'home_team_name': home,
            'away_team_name': away,
            'league_name': league,
        }

        # 获取让球盘+大小球数据（用于特征工程）
        try:
            from services.multi_source_fetcher import get_odds_api_handicap_totals
            handicap_info = get_odds_api_handicap_totals(home, away, league)
            if handicap_info:
                match_data['handicap_data'] = {
                    'avg_handicap': handicap_info.get('avg_handicap', 0.0),
                    'avg_handicap_home_odds': handicap_info.get('avg_handicap_home_odds', 1.9),
                    'avg_over_under_line': handicap_info.get('avg_over_line', 2.5),
                    'avg_over_odds': handicap_info.get('avg_over_odds', 1.9),
                    'avg_under_odds': handicap_info.get('avg_under_odds', 1.9),
                }
        except Exception:
            pass  # API失败时使用默认中性值

        odds_data = None
        if odds and len(odds) == 3:
            odds_data = {
                'odds': [str(o) for o in odds],
                'home_odds': float(odds[0]),
                'draw_odds': float(odds[1]),
                'away_odds': float(odds[2]),
            }

        is_close = self._is_close_match(home, away, odds)

        # 获取真实 form 和 H2H 数据
        team_form = None
        h2h_data = None
        if HybridPredictor._team_form_cache:
            hf = HybridPredictor._team_form_cache.get(home, {})
            af = HybridPredictor._team_form_cache.get(away, {})
            if hf or af:
                team_form = {home: hf, away: af}
        if HybridPredictor._h2h_cache:
            h2h_data = HybridPredictor._h2h_cache.get((home, away))

        # 获取各维度预测
        odds_pred = self._predict_from_odds(odds) if odds else None
        model_pred = self._predict_from_model(match_data, odds_data, team_form, h2h_data)
        ensemble_pred = self._predict_from_ensemble(match_data, odds_data, team_form, h2h_data)
        dc_pred = self._get_dc_prediction(home, away)
        ext_pred = self._get_external_consensus(home, away)
        elo_probs = self._elo_based_probs(home, away)

        # 基于真实 form 数据计算状态概率
        form_probs = None
        if team_form and hf and af:
            form_probs = self._form_based_probs(hf, af)

        # 球员+教练因子（有真实数据时参与融合）
        player_factor = None
        try:
            from services.player_data import get_match_player_factor
            pf = get_match_player_factor(home, away)
            if pf.get('has_data'):
                player_factor = pf
        except:
            pass

        # 球员因子概率（身价高+锋线强→主胜概率高）
        player_probs = None
        if player_factor:
            va = player_factor.get('home_value_advantage', 0)  # -1 to 1
            h_threat = player_factor.get('home_goal_threat', 50)
            a_threat = player_factor.get('away_goal_threat', 50)
            threat_diff = (h_threat - a_threat) / 100
            # 综合身价+进球威胁
            home_adv = va * 0.6 + threat_diff * 0.4
            hp = 0.40 + home_adv * 0.12
            ap = 0.30 - home_adv * 0.12
            dp = 0.30
            total = hp + dp + ap
            player_probs = {
                'home': round(hp / total * 100, 1),
                'draw': round(dp / total * 100, 1),
                'away': round(ap / total * 100, 1),
            }

        # ── 赔率变化检测：从DB查开盘→即时变化 ──
        odds_change = None  # {direction, magnitude, consensus}
        if odds and match_id:
            try:
                from app.db_helper import db_cursor
                with db_cursor() as cur:
                    cur.execute('''SELECT home_odds, draw_odds, away_odds, is_opening FROM odds
                        WHERE match_id=%s ORDER BY created_at''', (match_id,))
                    rows = cur.fetchall()

                if len(rows) >= 2:
                    opening = [float(r[0]) for r in rows if r[3] == 1]
                    latest = [float(r[0]) for r in rows if r[3] == 0]
                    if not opening: opening = [float(rows[0][0]), float(rows[0][1]), float(rows[0][2])]
                    else: opening = [opening[0], float(rows[0][1]), float(rows[0][2])] if len(opening) >= 1 else [float(rows[0][0]), float(rows[0][1]), float(rows[0][2])]
                    if not latest: latest = [float(rows[-1][0]), float(rows[-1][1]), float(rows[-1][2])]
                    else: latest = [latest[-1] if isinstance(latest, list) else float(rows[-1][0]), float(rows[-1][1]), float(rows[-1][2])]

                    # 简单平均所有bookmaker的开盘和最新
                    all_opening = {'home': [], 'draw': [], 'away': []}
                    all_latest = {'home': [], 'draw': [], 'away': []}
                    for r in rows:
                        ho, do, ao = float(r[0]), float(r[1]), float(r[2])
                        if r[3] == 1:  # opening
                            if ho > 1.01: all_opening['home'].append(ho)
                            if do > 1.01: all_opening['draw'].append(do)
                            if ao > 1.01: all_opening['away'].append(ao)
                        else:  # live
                            if ho > 1.01: all_latest['home'].append(ho)
                            if do > 1.01: all_latest['draw'].append(do)
                            if ao > 1.01: all_latest['away'].append(ao)

                    if all_opening['home'] and all_latest['home']:
                        avg = lambda lst: sum(lst)/len(lst) if lst else 0
                        h_ch = avg(all_latest['home']) - avg(all_opening['home'])
                        d_ch = avg(all_latest['draw']) - avg(all_opening['draw'])
                        a_ch = avg(all_latest['away']) - avg(all_opening['away'])
                        consensus = len(all_latest['home'])

                        # 确定变化方向
                        if abs(h_ch) > abs(a_ch):
                            direction = 'home_down' if h_ch < -0.05 else ('home_up' if h_ch > 0.05 else 'stable')
                            magnitude = abs(h_ch)
                        elif abs(a_ch) > abs(h_ch):
                            direction = 'away_down' if a_ch < -0.05 else ('away_up' if a_ch > 0.05 else 'stable')
                            magnitude = abs(a_ch)
                        else:
                            direction = 'stable'; magnitude = 0

                        odds_change = {'direction': direction, 'magnitude': magnitude, 'consensus': consensus}
            except:
                pass

        # ── 融合策略 ──
        final_probs = {'home': 0.0, 'draw': 0.0, 'away': 0.0}

        if odds_pred:
            dc_has_draw = dc_pred and dc_pred['prediction'] == 'draw' and dc_pred.get('probabilities', {}).get('draw', 0) > 30
            odds_is_home = odds_pred['prediction'] == 'home'

            if ensemble_pred and dc_pred:
                if dc_has_draw and odds_is_home:
                    odds_weight = 0.25; dc_weight = 0.18
                else:
                    odds_weight = 0.30; dc_weight = 0.15
                ensemble_weight = 0.25; elo_weight = 0.05; ext_weight = 0.10
                form_weight = 0.08 if form_probs else 0.0; model_weight = 0.07
            elif ensemble_pred:
                odds_weight = 0.35; ensemble_weight = 0.30; dc_weight = 0.0
                elo_weight = 0.08; ext_weight = 0.12
                form_weight = 0.08 if form_probs else 0.0; model_weight = 0.07
            elif form_probs:
                odds_weight = 0.42; model_weight = 0.20; dc_weight = 0.0
                ensemble_weight = 0.0; elo_weight = 0.08; ext_weight = 0.14; form_weight = 0.08
            else:
                odds_weight = 0.48; model_weight = 0.27; dc_weight = 0.0
                ensemble_weight = 0.0; elo_weight = 0.08; ext_weight = 0.17; form_weight = 0.0

            if odds_change and odds_change['magnitude'] > 0.08:
                ch_dir = odds_change['direction']
                ch_adj = min(0.10, odds_change['magnitude'] * 0.4)
                if ch_dir == 'home_down': odds_weight += ch_adj
                elif ch_dir == 'away_down': odds_weight += ch_adj
                elif ch_dir in ('home_up', 'away_up'): odds_weight = max(0.15, odds_weight - ch_adj)

            for key in ['home', 'draw', 'away']:
                final_probs[key] += odds_pred['probabilities'][key] * odds_weight

            if model_pred:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += model_pred['probabilities'][key] * model_weight
            else:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += elo_probs[key] * model_weight

            if ext_pred and ext_pred['total_sources'] > 0:
                ext_dir = ext_pred['prediction']
                final_probs[ext_dir] += ext_pred['confidence'] * ext_weight
                for key in ['home', 'draw', 'away']:
                    if key != ext_dir:
                        final_probs[key] += (100 - ext_pred['confidence']) / 2 * ext_weight
            else:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += elo_probs[key] * ext_weight

            for key in ['home', 'draw', 'away']:
                final_probs[key] += elo_probs[key] * elo_weight

            if form_probs:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += form_probs[key] * form_weight

            if ensemble_pred and ensemble_weight > 0:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += ensemble_pred['probabilities'][key] * ensemble_weight

            if dc_pred and dc_weight > 0:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += dc_pred['probabilities'][key] * dc_weight

            if player_probs:
                player_weight = 0.03
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += player_probs[key] * player_weight

        elif model_pred:
            if form_probs:
                model_weight = 0.50; elo_weight = 0.18; ext_weight = 0.17; form_weight = 0.15
            elif is_close:
                model_weight = 0.55; elo_weight = 0.25; ext_weight = 0.20; form_weight = 0.0
            else:
                model_weight = 0.65; elo_weight = 0.15; ext_weight = 0.20; form_weight = 0.0

            for key in ['home', 'draw', 'away']:
                final_probs[key] += model_pred['probabilities'][key] * model_weight
            if ext_pred and ext_pred['total_sources'] > 0:
                ext_dir = ext_pred['prediction']
                final_probs[ext_dir] += ext_pred['confidence'] * ext_weight
                for key in ['home', 'draw', 'away']:
                    if key != ext_dir:
                        final_probs[key] += (100 - ext_pred['confidence']) / 2 * ext_weight
            else:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += elo_probs[key] * ext_weight
            for key in ['home', 'draw', 'away']:
                final_probs[key] += elo_probs[key] * elo_weight
            if form_probs:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += form_probs[key] * form_weight
            if ensemble_pred:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += ensemble_pred['probabilities'][key] * 0.20
            if dc_pred:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] += dc_pred['probabilities'][key] * 0.15
        else:
            if dc_pred:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] = dc_pred['probabilities'][key] * 0.30 + elo_probs[key] * 0.70
            elif form_probs:
                for key in ['home', 'draw', 'away']:
                    final_probs[key] = form_probs[key] * 0.35 + elo_probs[key] * 0.65
            elif ext_pred and ext_pred['total_sources'] > 0:
                ext_dir = ext_pred['prediction']
                for key in ['home', 'draw', 'away']:
                    final_probs[key] = elo_probs[key] * 0.6
                final_probs[ext_dir] += ext_pred['confidence'] * 0.4
            else:
                final_probs = elo_probs.copy()

        # 归一化
        total = sum(final_probs.values())
        if total > 0:
            final_probs = {k: round(v / total * 100, 1) for k, v in final_probs.items()}
        else:
            final_probs = {'home': 33.3, 'draw': 33.3, 'away': 33.3}

        # ── 平局修正：只在有真实赔率数据时才修正 ──
        odds_implied_draw = 0
        has_real_odds = odds is not None  # 是否有真实赔率数据
        
        if odds_pred:
            odds_implied_draw = odds_pred['probabilities'].get('draw', 0)

        # 只在有真实赔率时才进行平局修正
        if has_real_odds and odds_pred and odds_implied_draw > 0:
            odds_h = odds_pred['probabilities'].get('home', 0)
            odds_a = odds_pred['probabilities'].get('away', 0)
            
            # 平局赔率
            draw_odds_val = float(odds[1]) if len(odds) > 1 else 3.5
            
            # 只在实力接近时才提升平局概率
            strength_gap = abs(odds_h - odds_a)
            
            # 规则1: 赔率平局概率 > 22% 且实力非常接近（差距<8%）→ 平局信号
            if odds_implied_draw >= 22 and strength_gap < 8:
                draw_boost = min(10.0, (odds_implied_draw - 20) * 0.6)
                final_probs['draw'] = final_probs.get('draw', 0) + draw_boost
                if final_probs.get('home', 0) > final_probs.get('away', 0):
                    final_probs['home'] = max(0, final_probs.get('home', 0) - draw_boost * 0.55)
                    final_probs['away'] = max(0, final_probs.get('away', 0) - draw_boost * 0.45)
                else:
                    final_probs['home'] = max(0, final_probs.get('home', 0) - draw_boost * 0.45)
                    final_probs['away'] = max(0, final_probs.get('away', 0) - draw_boost * 0.55)
            
            # 规则2: 平赔 < 3.2 且实力接近（差距<10%）→ 平局信号
            elif draw_odds_val < 3.2 and strength_gap < 10:
                draw_boost = min(12.0, (3.5 - draw_odds_val) * 6)
                final_probs['draw'] = final_probs.get('draw', 0) + draw_boost
                if final_probs.get('home', 0) > final_probs.get('away', 0):
                    final_probs['home'] = max(0, final_probs.get('home', 0) - draw_boost * 0.55)
                    final_probs['away'] = max(0, final_probs.get('away', 0) - draw_boost * 0.45)
                else:
                    final_probs['home'] = max(0, final_probs.get('home', 0) - draw_boost * 0.45)
                    final_probs['away'] = max(0, final_probs.get('away', 0) - draw_boost * 0.55)

        if dc_pred:
            dc_draw_p = dc_pred['probabilities'].get('draw', 0)
            if dc_draw_p > 32:
                dc_w = min(0.15, (dc_draw_p - 32) / 100)
                for key in ['home', 'draw', 'away']:
                    final_probs[key] = final_probs[key] * (1 - dc_w) + dc_pred['probabilities'][key] * dc_w

        draw_p = final_probs.get('draw', 0)
        if is_close and draw_p < 25:
            boost = min(3.0, (25 - draw_p) * 0.3)
            final_probs['draw'] = draw_p + boost
            top_key = max(final_probs, key=final_probs.get)
            if top_key != 'draw':
                final_probs[top_key] -= boost * 0.55
                others = [k for k in ['home', 'draw', 'away'] if k != top_key and k != 'draw']
                if others: final_probs[others[0]] -= boost * 0.45

        # 重新归一化
        total = sum(final_probs.values())
        if total > 0:
            final_probs = {k: round(v / total * 100, 1) for k, v in final_probs.items()}

        sorted_probs = sorted(final_probs.values(), reverse=True)
        prob_gap = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0

        # ── 输出校准层（基于国际研究：Shin+DixonColes+Platt启发）──
        final_probs = self._calibrate_output(
            final_probs, odds_pred, is_close, prob_gap,
            ensemble_pred, dc_pred, model_pred, elo_probs
        )

        sorted_probs = sorted(final_probs.values(), reverse=True)
        prob_gap = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else 0

        # 4) 最终决策：简单规则
        final_draw_p = final_probs.get('draw', 0)
        final_home_p = final_probs.get('home', 0)
        final_away_p = final_probs.get('away', 0)

        # 获取 ML 模型的预测
        ml_pred = model_pred['prediction'] if model_pred else None
        ml_conf = model_pred['confidence'] if model_pred else 0

        # 规则1: ML模型高度自信(>50%) → 直接信任ML
        if ml_pred == 'away' and ml_conf > 50:
            prediction = 'away'
            confidence = final_away_p
        elif ml_pred == 'home' and ml_conf > 50:
            prediction = 'home'
            confidence = final_home_p
        # 规则2: 有真实赔率且平赔接近最高 → 平局
        elif has_real_odds and odds_pred and odds_implied_draw >= max(odds_pred['probabilities'].get('home', 0), odds_pred['probabilities'].get('away', 0)) - 3:
            prediction = 'draw'
            confidence = final_draw_p
        # 规则3: 概率差距极小且平局有基础 → 平局
        elif prob_gap < 3 and final_draw_p >= 25:
            prediction = 'draw'
            confidence = final_draw_p
        # 规则4: 直接使用融合后概率最高者
        else:
            prediction = max(final_probs, key=final_probs.get)
            confidence = final_probs[prediction]

        # 兜底纠正1：赔率高度明确指向一方，模型却预测另一方 → 信市场
        # 市场极明确(spread>1.5)时降阈到50，正常情况阈60
        if odds_pred and odds_pred.get('prediction'):
            odds_dir = odds_pred['prediction']
            odds_conf = odds_pred['probabilities'].get(odds_dir, 0)
            override_threshold = 50 if market_very_clear else 60
            if odds_dir in ('home', 'away') and odds_conf > override_threshold and prediction != odds_dir:
                prediction = odds_dir
                confidence = final_probs[prediction]

        # 兜底纠正2：赔率胶着（无一方>50%）但实力分差距明显 → 信实力分
        if odds_pred and odds_pred.get('prediction'):
            max_odds_p = max(odds_pred['probabilities'].values())
            try:
                from services.prediction_service import PredictionService
                _strength = PredictionService.TEAM_STRENGTH
            except:
                _strength = {}
            _def_str = lambda name: int(hashlib.md5(name.encode()).hexdigest()[:4], 16) % 13 + 62
            hs = _strength.get(home, _def_str(home))
            aws = _strength.get(away, _def_str(away))
            strength_gap = hs - aws
            if max_odds_p < 50 and abs(strength_gap) >= 10:
                if strength_gap > 0 and prediction != 'home':
                    prediction = 'home'; confidence = final_probs['home']
                elif strength_gap < 0 and prediction != 'away':
                    prediction = 'away'; confidence = final_probs['away']

        # 生成预测理由
        reasons = self._build_reasons(
            prediction, confidence, final_probs,
            home, away, is_close, prob_gap,
            odds_pred, model_pred, ext_pred, elo_probs
        )

        # 从 DC 模型获取真实比分预测
        predicted_score = dc_pred.get('predicted_score', '') if dc_pred else ''
        expected_goals = dc_pred.get('expected_goals', {}) if dc_pred else {}
        if not predicted_score:
            predicted_score = self._score_from_probs(final_probs, prediction)

        return {
            'prediction': prediction,
            'prediction_name': RESULT_CN[prediction],
            'confidence': confidence,
            'probabilities': final_probs,
            'predicted_score': predicted_score,
            'expected_goals': expected_goals,
            'confidence_level': '高' if confidence >= 65 else ('中' if confidence >= 55 else '低'),
            'is_close_match': is_close,
            'prob_gap': round(prob_gap, 1),
            'reasons': reasons,
            'components': {
                'odds': odds_pred,
                'model': model_pred,
                'external': ext_pred,
                'elo': elo_probs,
                'dc': dc_pred,
            },
            'has_odds': odds_pred is not None,
        }

    @staticmethod
    def _score_from_probs(probs, prediction):
        """根据概率差距生成合理的比分预测，避免永远2-0"""
        home_p = probs.get('home', 33)
        away_p = probs.get('away', 33)
        draw_p = probs.get('draw', 33)

        if prediction == 'draw':
            if draw_p > 38:
                return '1-1'
            elif draw_p > 30:
                return '0-0'
            return '2-2'

        if prediction == 'home':
            gap = home_p - away_p
            if gap > 35:
                return '3-0'
            elif gap > 22:
                return '2-0'
            elif gap > 12:
                return '2-1'
            elif gap > 5:
                return '1-0'
            return '3-2'

        if prediction == 'away':
            gap = away_p - home_p
            if gap > 35:
                return '0-3'
            elif gap > 22:
                return '0-2'
            elif gap > 12:
                return '1-2'
            elif gap > 5:
                return '0-1'
            return '2-3'

    def _calibrate_output(self, probs, odds_pred, is_close, prob_gap,
                          ensemble_pred, dc_pred, model_pred, elo_probs):
        """
        输出概率校准层 — 融合国外主流校准技术

        三个校准步骤：
        1. 市场校准 (Shin): 有赔率时，向市场隐含概率小幅回归
        2. 主场偏差修正: 全球主胜率约44%，过度偏向主胜需修正
        3. 平局依赖修正 (Dixon-Coles τ启发): 低比分依赖 → 平局概率提升
        4. 类别先验校准 (Threshold Moving): 基于真实分布调整决策边界

        参考: Dixon & Coles (1997), Shin (1993), Platt (1999),
              Kuhn & Johnson (2013) "Applied Predictive Modeling" Ch.11
        """
        calibrated = {k: v for k, v in probs.items()}

        # ─── 校准0: 温度缩放 (Temperature Scaling) ───
        # 降低模型过度自信，使概率分布更接近真实频率
        temp = 1.25  # T>1 → 分布更均匀
        cal_sum = 0.0
        for key in ['home', 'draw', 'away']:
            calibrated[key] = calibrated[key] ** (1.0 / temp)
            cal_sum += calibrated[key]
        for key in ['home', 'draw', 'away']:
            calibrated[key] = calibrated[key] / cal_sum * 100

        # ─── 校准1: 市场回归 ───
        if odds_pred:
            odds_home = odds_pred['probabilities'].get('home', 0)
            model_home = calibrated.get('home', 0)
            if odds_pred['prediction'] == 'home' and model_home > odds_home:
                market_trust = 0.20
            else:
                market_trust = 0.35
            for key in ['home', 'draw', 'away']:
                market_p = odds_pred['probabilities'].get(key, calibrated[key])
                calibrated[key] = calibrated[key] * (1 - market_trust) + market_p * market_trust

        # ─── 校准2: 主场偏差修正 ───
        home_p = calibrated.get('home', 0)
        draw_p = calibrated.get('draw', 0)
        away_p = calibrated.get('away', 0)

        odds_confirms_home = odds_pred and odds_pred['prediction'] == 'home' and \
                             odds_pred['probabilities'].get('home', 0) > 50

        home_threshold = 55 if odds_confirms_home else 46

        if home_p > home_threshold and away_p > 8:
            excess = home_p - home_threshold
            correction = excess * 0.40
            calibrated['home'] = home_p - correction
            calibrated['draw'] = draw_p + correction * 0.55
            calibrated['away'] = away_p + correction * 0.45

        # ─── 校准3: 平局依赖修正 (Dixon-Coles τ 启发) ───
        draw_p = calibrated.get('draw', 0)

        if is_close:
            if draw_p < 24:
                tau_boost = (24 - draw_p) * 0.50
                calibrated['draw'] = draw_p + tau_boost
                top_key = max(calibrated, key=calibrated.get)
                if top_key != 'draw':
                    calibrated[top_key] -= tau_boost * 0.6
                    others = [k for k in ['home', 'draw', 'away'] if k != top_key and k != 'draw']
                    if others: calibrated[others[0]] -= tau_boost * 0.4

        if dc_pred:
            dc_draw_p = dc_pred['probabilities'].get('draw', 0)
            if dc_draw_p > 28:
                dc_boost = min(4.0, (dc_draw_p - 28) * 0.25)
                calibrated['draw'] = calibrated.get('draw', 0) + dc_boost
                top_key = max(calibrated, key=calibrated.get)
                if top_key != 'draw':
                    calibrated[top_key] -= dc_boost * 0.65
                    others = [k for k in ['home', 'draw', 'away'] if k != top_key and k != 'draw']
                    if others: calibrated[others[0]] -= dc_boost * 0.35

        # 平局硬底
        if calibrated.get('draw', 0) < 16:
            deficit = 16 - calibrated['draw']
            calibrated['draw'] = 16
            top_key = max(calibrated, key=lambda k: calibrated[k] if k != 'draw' else -1)
            calibrated[top_key] -= deficit * 0.65
            others = [k for k in ['home', 'draw', 'away'] if k != top_key and k != 'draw']
            if others: calibrated[others[0]] -= deficit * 0.35

        # 确保无负值
        for key in ['home', 'draw', 'away']:
            calibrated[key] = max(0.5, calibrated[key])

        # 归一化
        total = sum(calibrated.values())
        return {k: round(v / total * 100, 1) for k, v in calibrated.items()}

    def _build_reasons(self, prediction, confidence, probs, home, away, is_close, prob_gap,
                       odds_pred, model_pred, ext_pred, elo_probs):
        """生成预测理由"""
        reasons = []
        hs = self._get_elo_strength(home)
        aws = self._get_elo_strength(away)

        # 1. 赔率信号
        if odds_pred:
            if odds_pred['prediction'] == prediction:
                reasons.append(f"赔率市场一致看好{RESULT_CN[prediction]}（隐含概率{odds_pred['probabilities'][prediction]:.0f}%）")
            else:
                reasons.append(f"赔率指向{RESULT_CN[odds_pred['prediction']]}，但综合模型修正为{RESULT_CN[prediction]}")

        # 2. 实力对比
        diff = hs - aws
        if diff > 8:
            reasons.append(f"{home}实力明显占优（评分{hs:.0f} vs {aws:.0f}）")
        elif diff > 4:
            reasons.append(f"{home}实力略占上风（评分{hs:.0f} vs {aws:.0f}）")
        elif diff < -8:
            reasons.append(f"{away}实力明显占优（评分{aws:.0f} vs {hs:.0f}）")
        elif diff < -4:
            reasons.append(f"{away}实力略占上风（评分{aws:.0f} vs {hs:.0f}）")
        else:
            reasons.append(f"两队实力接近（{home}{hs:.0f} vs {away}{aws:.0f}）")

        # 3. 外部共识
        if ext_pred and ext_pred['total_sources'] > 0:
            total = ext_pred['total_sources']
            ep = ext_pred['prediction']
            if ep == prediction:
                reasons.append(f"{total}个外部预测源一致支持{RESULT_CN[prediction]}")
            else:
                reasons.append(f"{total}个外部源倾向{RESULT_CN[ep]}，与当前预测存在分歧")

        # 4. 胶着比赛特别说明
        if prob_gap < 8:
            reasons.append(f"各结果概率接近(差距仅{prob_gap:.0f}%)，平局可能性不容忽视")
            if confidence < 45:
                reasons.append("置信度较低，任何结果都有可能，建议观望")
        elif is_close:
            reasons.append("实力接近，平局可能性较高，建议谨慎")

        # 5. 主场因素
        if prediction == 'home' and diff > -5:
            reasons.append(f"{home}坐拥主场优势")

        return reasons


def evaluate_on_test_set():
    """在28场有真实赔率的比赛上评估混合预测器"""
    results_file = os.path.join(DATA_DIR, 'jczq_results.json')
    if not os.path.exists(results_file):
        print("没有找到测试数据")
        return

    with open(results_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    predictor = HybridPredictor()

    correct_odds = 0
    correct_hybrid = 0
    correct_close = 0
    total_close = 0
    total = 0

    for m in data:
        home = m.get('home', '')
        away = m.get('away', '')
        league = m.get('league', '')
        odds = m.get('odds', [])
        full_score = m.get('full_score', '')

        if not full_score or ':' not in full_score:
            continue
        if not odds or len(odds) != 3:
            continue

        parts = full_score.split(':')
        hg, ag = int(parts[0]), int(parts[1])
        if hg > ag:
            actual = 'home'
        elif hg < ag:
            actual = 'away'
        else:
            actual = 'draw'

        odds_pred = predictor._predict_from_odds(odds)
        hybrid_pred = predictor.predict(home, away, league, odds)

        total += 1
        if odds_pred['prediction'] == actual:
            correct_odds += 1
        if hybrid_pred['prediction'] == actual:
            correct_hybrid += 1

        if hybrid_pred.get('is_close_match'):
            total_close += 1
            if hybrid_pred['prediction'] == actual:
                correct_close += 1

    odds_acc = round(correct_odds / total * 100, 1) if total > 0 else 0
    hybrid_acc = round(correct_hybrid / total * 100, 1) if total > 0 else 0
    close_acc = round(correct_close / total_close * 100, 1) if total_close > 0 else 0

    print("=" * 60)
    print(f"评估结果 ({total} 场有真实赔率)")
    print("=" * 60)
    print(f"赔率基线准确率: {odds_acc}% ({correct_odds}/{total})")
    print(f"混合预测准确率: {hybrid_acc}% ({correct_hybrid}/{total})")
    print(f"其中实力接近 ({total_close} 场): {close_acc}%")
    print()

    # Show where hybrid differs from odds
    for m in data:
        home = m.get('home', '')
        away = m.get('away', '')
        odds = m.get('odds', [])
        if not odds or len(odds) != 3:
            continue
        full_score = m.get('full_score', '')
        if ':' not in full_score:
            continue
        parts = full_score.split(':')
        hg, ag = int(parts[0]), int(parts[1])
        actual = 'home' if hg > ag else ('away' if hg < ag else 'draw')

        op = predictor._predict_from_odds(odds)
        hp = predictor.predict(home, away, m.get('league', ''), odds)

        if op['prediction'] != hp['prediction']:
            o_ok = 'OK' if op['prediction'] == actual else 'XX'
            h_ok = 'OK' if hp['prediction'] == actual else 'XX'
            print(f"  {home} vs {away}: 实际={RESULT_CN[actual]} | 赔率={RESULT_CN[op['prediction']]}[{o_ok}] | 混合={RESULT_CN[hp['prediction']]}[{h_ok}] | probs={hp['probabilities']}")

    return odds_acc, hybrid_acc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    odds_acc, hybrid_acc = evaluate_on_test_set()
