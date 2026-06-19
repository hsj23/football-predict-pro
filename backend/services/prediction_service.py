"""
综合预测服务 - 多维度分析引擎
维度: 实力(22%) + 状态(17%) + 交锋(11%) + 赔率(14%) + 盘口(9%)
      + 外围(9%) + 新闻(9%) + 主客场(7%) + 进球效率(7%)
赔率维度权重提升至14% — 赔率是市场信号的直接反映
"""
import logging
import hashlib
import math
import os
import sys
import json
import threading

logger = logging.getLogger(__name__)

# ── 历史比赛数据缓存（从 training_data.json 加载） ──
_historical_cache = None
_historical_cache_lock = threading.Lock()


def _get_player_value_info(team_name):
    """获取球队球员身价信息"""
    try:
        from services.multi_source_fetcher import load_player_values
        all_values = load_player_values()
        if team_name in all_values:
            players = all_values[team_name]
            total = round(sum(v for _, v in players), 1)
            return {
                'total_value': total,
                'unit': '亿欧元',
                'top_players': [{'name': n, 'value': v} for n, v in players[:5]],
            }
    except:
        pass
    return None


def _load_historical_data():
    """加载 training_data.json 并建立队伍索引，缓存到内存"""
    global _historical_cache
    if _historical_cache is not None:
        return _historical_cache

    with _historical_cache_lock:
        if _historical_cache is not None:
            return _historical_cache

        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        training_file = os.path.join(data_dir, 'training_data.json')

        team_matches = {}   # team_name -> [(date, scored, conceded, is_home), ...]
        h2h_index = {}      # (team_a, team_b) -> [(date, home_score, away_score), ...] (team_a is home)

        if os.path.exists(training_file):
            try:
                with open(training_file, 'r', encoding='utf-8') as f:
                    matches = json.load(f)

                for m in matches:
                    home = m.get('home', '').strip()
                    away = m.get('away', '').strip()
                    hs = m.get('home_score')
                    ags = m.get('away_score')
                    date = m.get('date', '')
                    if not home or not away or hs is None or ags is None:
                        continue
                    hs, ags = int(hs), int(ags)

                    # 主队视角
                    team_matches.setdefault(home, []).append((date, hs, ags, True))
                    # 客队视角
                    team_matches.setdefault(away, []).append((date, ags, hs, False))

                    # H2H 索引
                    key = (home, away)
                    h2h_index.setdefault(key, []).append((date, hs, ags))

                # 按日期降序排列
                for t in team_matches:
                    team_matches[t].sort(key=lambda x: x[0], reverse=True)
                for k in h2h_index:
                    h2h_index[k].sort(key=lambda x: x[0], reverse=True)

                logger.info(f"已加载 {len(matches)} 场历史比赛，{len(team_matches)} 支队伍")
            except Exception as e:
                logger.warning(f"加载历史比赛数据失败: {e}")
                team_matches, h2h_index = {}, {}

        _historical_cache = (team_matches, h2h_index)
        return _historical_cache


def _get_real_form(team_name, num_matches=5):
    """从真实历史数据中提取近期状态（W/D/L），优先查 DB，其次查 training_data.json"""
    # 1) 尝试从数据库获取最新数据
    try:
        from app.db_helper import db_cursor
        with db_cursor() as cur:
            cur.execute(
                "SELECT home_team_name, away_team_name, home_score, away_score, match_time "
                "FROM matches WHERE (home_team_name=%s OR away_team_name=%s) "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL "
                "ORDER BY match_time DESC LIMIT %s",
                (team_name, team_name, num_matches))
            db_rows = cur.fetchall()

        if db_rows:
            results = []
            pts = 0
            for home, away, hs, ags, _ in db_rows:
                hs, ags = int(hs), int(ags)
                if home == team_name:
                    scored, conceded = hs, ags
                else:
                    scored, conceded = ags, hs
                if scored > conceded:
                    results.append('W'); pts += 3
                elif scored == conceded:
                    results.append('D'); pts += 1
                else:
                    results.append('L')
            if results:
                return {'results': results, 'pts': pts, 'source': 'db'}
    except Exception as e:
        logger.debug(f"DB form query failed for {team_name}: {e}")

    # 2) 从 training_data.json 获取历史数据
    team_matches, _ = _load_historical_data()
    if team_name in team_matches:
        recent = team_matches[team_name][:num_matches]
        if recent:
            results = []
            pts = 0
            for date, scored, conceded, is_home in recent:
                if scored > conceded:
                    results.append('W'); pts += 3
                elif scored == conceded:
                    results.append('D'); pts += 1
                else:
                    results.append('L')
            return {'results': results, 'pts': pts, 'source': 'historical'}

    # 3) 无数据时返回空，让调用方自行处理
    return None


def _get_real_h2h(home_team, away_team, num_matches=8):
    """从真实历史数据中提取交锋记录，优先查 DB，其次查 training_data.json"""
    # 1) 尝试数据库
    try:
        from app.db_helper import db_cursor
        with db_cursor() as cur:
            cur.execute(
                "SELECT home_team_name, home_score, away_score FROM matches "
                "WHERE ((home_team_name=%s AND away_team_name=%s) OR (home_team_name=%s AND away_team_name=%s)) "
                "AND home_score IS NOT NULL AND away_score IS NOT NULL "
                "ORDER BY match_time DESC LIMIT %s",
                (home_team, away_team, away_team, home_team, num_matches))
            db_rows = cur.fetchall()

        if db_rows:
            hw = dw = aw = 0
            for home, hs, ags in db_rows:
                hs, ags = int(hs), int(ags)
                if home == home_team:
                    if hs > ags: hw += 1
                    elif hs == ags: dw += 1
                    else: aw += 1
                else:
                    if ags > hs: hw += 1
                    elif ags == hs: dw += 1
                    else: aw += 1
            total = hw + dw + aw
            if total > 0:
                return {'total': total, 'home_wins': hw, 'draws': dw, 'away_wins': aw, 'source': 'db'}
    except Exception as e:
        logger.debug(f"DB H2H query failed for {home_team} vs {away_team}: {e}")

    # 2) 从 training_data.json 查找
    _, h2h_index = _load_historical_data()
    key = (home_team, away_team)
    rev_key = (away_team, home_team)

    h2h_matches = []
    if key in h2h_index:
        h2h_matches.extend([(date, hs, ags, True) for date, hs, ags in h2h_index[key]])
    if rev_key in h2h_index:
        h2h_matches.extend([(date, ags, hs, False) for date, hs, ags in h2h_index[rev_key]])

    if h2h_matches:
        h2h_matches.sort(key=lambda x: x[0], reverse=True)
        h2h_matches = h2h_matches[:num_matches]
        hw = dw = aw = 0
        for date, hs, ags, home_is_home_team in h2h_matches:
            if home_is_home_team:
                if hs > ags: hw += 1
                elif hs == ags: dw += 1
                else: aw += 1
            else:
                if ags > hs: hw += 1
                elif ags == hs: dw += 1
                else: aw += 1
        total = hw + dw + aw
        if total > 0:
            return {'total': total, 'home_wins': hw, 'draws': dw, 'away_wins': aw, 'source': 'historical'}

    return None


def _get_news_factors(home_team, away_team, home_strength, away_strength):
    """获取真实伤病/新闻数据，没有则返回空（不造假）"""
    factors = {
        'home_injuries': [],
        'away_injuries': [],
        'home_suspensions': 0,
        'away_suspensions': 0,
        'weather': '',
        'weather_impact': 0,
        'home_morale': 0,
        'away_morale': 0,
    }
    # 从真实伤病数据加载（Fantasy PL API + injuries.json）
    try:
        from services.auto_data_service import load_latest_data
        injuries = load_latest_data('injuries')
        if injuries and injuries.get('data'):
            inj_data = injuries['data']
            for name in [home_team, away_team]:
                if name not in inj_data:
                    continue
                injured = inj_data[name]
                if name == home_team:
                    factors['home_injuries'] = injured[:3]
                    factors['home_morale'] -= min(len(injured), 3)
                else:
                    factors['away_injuries'] = injured[:3]
                    factors['away_morale'] -= min(len(injured), 3)
    except:
        pass
    return factors


def _try_fetch_forebet(home_team, away_team):
    """获取外部多源共识预测"""
    result = {'source': 'external', 'available': False, 'prediction': None, 'confidence': 50, 'sources': []}
    try:
        from services.external_aggregator import get_consensus_prediction
        consensus = get_consensus_prediction(home_team, away_team)
        if consensus and consensus['total_sources'] > 0:
            result['available'] = True
            result['prediction'] = consensus['prediction']
            result['confidence'] = consensus['confidence']
            src_count = consensus['total_sources']
            hv = consensus['home_votes']; dv = consensus['draw_votes']; av = consensus['away_votes']
            result['sources'] = str(src_count) + ' sources'
            result['votes'] = 'H' + str(hv) + ' D' + str(dv) + ' A' + str(av)
    except:
        pass
    return result


class PredictionService:
    """综合预测服务"""

    # 球队实力评分 — 从共享数据导入
    from data.team_data import TEAM_STRENGTH

    HOME_ADVANTAGE = 4

    def _default_strength(self, team_name):
        """为未知球队生成基于队名的确定性分数，避免所有未知队相同"""
        h = int(hashlib.md5(team_name.encode()).hexdigest()[:4], 16)
        return 62 + (h % 13)  # 62-74 之间的确定性分数

    def _get_real_strength(self, team_name, base_strength):
        """从历史比赛数据中计算球队真实实力修正"""
        try:
            from app.db_helper import db_cursor
            with db_cursor() as cur:
                cur.execute('''
                    SELECT home_score, away_score, home_team_name, away_team_name
                    FROM matches WHERE (home_team_name=%s OR away_team_name=%s)
                    AND status='finished' AND home_score IS NOT NULL
                    ORDER BY match_time DESC LIMIT 10
                ''', (team_name, team_name))
                rows = cur.fetchall()

            if not rows or len(rows) < 3:
                return base_strength  # 数据不足，用基础评分

            wins = draws = losses = gf = ga = 0
            for hs, aws, ht, at in rows:
                if not hs or not aws: continue
                if ht == team_name:  # 主队
                    gf += hs; ga += aws
                    if hs > aws: wins += 1
                    elif hs == aws: draws += 1
                    else: losses += 1
                else:  # 客队
                    gf += aws; ga += hs
                    if aws > hs: wins += 1
                    elif aws == hs: draws += 1
                    else: losses += 1

            total = wins + draws + losses
            if total == 0: return base_strength

            # 胜率贡献
            win_rate = wins / total
            # 场均进球-失球差
            gd_per_game = (gf - ga) / total
            # 修正量: 胜率50%为基准，每偏离10%±2分；净胜球每+1球±3分
            adj = (win_rate - 0.5) * 20 + gd_per_game * 3
            # 限制修正幅度在±8分内
            adj = max(-8, min(8, adj))

            return round(base_strength + adj)
        except Exception as e:
            return base_strength

    def generate_prediction(self, home_team, away_team, league='', match_id=None, historical=False, preloaded_odds=None):
        """
        综合多维度预测
        优先使用HybridPredictor (ML模型+赔率+外部共识)
        降级到传统多维度加权方法
        preloaded_odds: 可选，批量预加载的赔率 [home, draw, away]
        """
        # === 优先使用混合预测器 (ML + 赔率 + 外部共识) ===
        try:
            # 线程安全的HybridPredictor缓存（避免每请求重复加载模型）
            if not hasattr(self, '_hp_local'):
                import threading as _thr
                self._hp_local = _thr.local()
            if not hasattr(self._hp_local, 'predictor'):
                from ml.hybrid_predictor import HybridPredictor
                self._hp_local.predictor = HybridPredictor()
            predictor = self._hp_local.predictor

            # 获取赔率（优先使用预加载，否则查DB）
            odds = preloaded_odds
            if odds is None and match_id:
                try:
                    from app.db_helper import db_cursor
                    with db_cursor() as cur:
                        cur.execute("SELECT home_odds, draw_odds, away_odds FROM odds WHERE match_id=%s LIMIT 1", (match_id,))
                        row = cur.fetchone()
                        if row and row[0]:
                            odds = [float(row[0]), float(row[1]), float(row[2])]
                except Exception as e:
                    logger.debug(f"Odds fetch failed for {match_id}: {e}")

            # 获取真实盘口
            real_handicap = None
            if match_id:
                try:
                    from app.db_helper import db_cursor
                    with db_cursor() as cur:
                        cur.execute('SELECT handicap FROM odds WHERE match_id=%s AND bookmaker=%s AND handicap IS NOT NULL LIMIT 1',
                                   (match_id, '500_handicap'))
                        hc_row = cur.fetchone()
                        if hc_row and hc_row[0] is not None:
                            real_handicap = float(hc_row[0])
                except Exception as e:
                    logger.debug(f"Handicap fetch failed for {match_id}: {e}")
            predictor._real_handicap = real_handicap

            hybrid_result = predictor.predict(home_team, away_team, league, odds, match_id)

            # 构建完整的分析数据
            extras = self._build_hybrid_extras(hybrid_result, home_team, away_team, league, match_id)

            return {
                'prediction': {
                    'prediction': hybrid_result['prediction'],
                    'prediction_name': hybrid_result['prediction_name'],
                    'confidence': hybrid_result['confidence'],
                    'probabilities': hybrid_result['probabilities'],
                    'confidence_level': hybrid_result['confidence_level'],
                    'predicted_score': hybrid_result.get('predicted_score') or self._predict_score_from_probs(hybrid_result['probabilities'], hybrid_result['prediction']),
                    'engine': 'hybrid_v2',
                    'has_odds': hybrid_result.get('has_odds', False),
                    'is_close_match': hybrid_result.get('is_close_match', False),
                    'prob_gap': hybrid_result.get('prob_gap', 0),
                },
                **extras
            }
        except Exception as e:
            logger.warning(f"HybridPredictor不可用 ({e})，使用传统方法")
            # 降级到传统预测方法
            return self._generate_prediction_traditional(home_team, away_team, league, match_id, historical)

    def _build_hybrid_extras(self, hybrid_result, home_team, away_team, league, match_id):
        """构建混合预测器的完整补充数据（平台预测+赔率+队伍分析+交锋+摘要）"""
        hs = self.TEAM_STRENGTH.get(home_team, self._default_strength(home_team))
        aws = self.TEAM_STRENGTH.get(away_team, self._default_strength(away_team))
        hs = self._get_real_strength(home_team, hs)
        aws = self._get_real_strength(away_team, aws)

        # 平台预测
        ext = _try_fetch_forebet(home_team, away_team)
        probs_raw = {'home': 50.0, 'draw': 28.0, 'away': 22.0}
        diff = hs - aws
        platforms = self._platform_predictions(probs_raw, diff, hs, aws, match_id, home_team, away_team)
        plat_votes = self._count_platform_votes(platforms, probs_raw)

        # 赔率分析
        odds_analysis = self._calc_odds(diff, match_id, home_team, away_team)

        # 队伍分析
        home_form = self._get_form(home_team)
        away_form = self._get_form(away_team)
        team_analysis = {
            'home': {
                'strength': hs,
                'form': home_form,
                'win_rate': round(30 + (hs - 60) * 0.7, 1),
            },
            'away': {
                'strength': aws,
                'form': away_form,
                'win_rate': round(30 + (aws - 60) * 0.7, 1),
            },
        }

        # 交锋分析
        h2h = self._calc_h2h(home_team, away_team, hs, aws)

        # 新闻分析
        news = _get_news_factors(home_team, away_team, hs, aws)

        # 分析摘要
        actual_probs = hybrid_result.get('probabilities', {'home':50,'draw':28,'away':22})
        summary = self._build_summary(
            home_team, away_team, hs, aws, diff,
            actual_probs,
            h2h, odds_analysis, home_form, away_form, news, ext,
            hybrid_result.get('is_close_match', False),
            hybrid_result.get('prob_gap', 10),
            final_pred=hybrid_result.get('prediction'),
            final_conf=hybrid_result.get('confidence')
        )

        return {
            'platform_predictions': platforms,
            'platform_votes': plat_votes,
            'odds_analysis': odds_analysis,
            'odds_change_signal': odds_analysis.get('odds_change_signal'),
            'team_analysis': team_analysis,
            'h2h_analysis': h2h,
            'analysis_summary': summary,
            'news_analysis': {
                'home': {'injuries': len(news['home_injuries']), 'injury_detail': news['home_injuries'],
                         'suspensions': news['home_suspensions'], 'morale': news['home_morale']},
                'away': {'injuries': len(news['away_injuries']), 'injury_detail': news['away_injuries'],
                         'suspensions': news['away_suspensions'], 'morale': news['away_morale']},
            },
        }

    def _predict_score_from_probs(self, probs, prediction):
        """根据概率分布预测比分 — 确保比分与预测类型一致"""
        common_scores = {
            'home': [('2-0', 0.18), ('2-1', 0.16), ('1-0', 0.17), ('3-1', 0.12), ('3-0', 0.10)],
            'draw': [('1-1', 0.45), ('0-0', 0.25), ('2-2', 0.20), ('3-3', 0.10)],
            'away': [('0-2', 0.18), ('1-2', 0.16), ('0-1', 0.17), ('1-3', 0.12), ('0-3', 0.10)],
        }
        scores = common_scores.get(prediction, [('1-0', 0.5), ('1-1', 0.3), ('0-1', 0.2)])
        best_score = max(scores, key=lambda x: x[1])[0]
        # 安全校验：比分必须与预测结果一致
        if not self._validate_score_match(best_score, prediction):
            return self._default_score(prediction)
        return best_score

    @staticmethod
    def _validate_score_match(score, prediction):
        """验证比分与预测结果一致"""
        if not score or '-' not in score:
            return False
        try:
            h, a = map(int, score.split('-'))
        except ValueError:
            return False
        if prediction == 'home':
            return h > a
        elif prediction == 'away':
            return a > h
        elif prediction == 'draw':
            return h == a
        return True

    @staticmethod
    def _default_score(prediction):
        """预测结果的默认比分"""
        return {'home': '2-0', 'draw': '1-1', 'away': '0-2'}.get(prediction, '1-0')

    def _generate_prediction_traditional(self, home_team, away_team, league='', match_id=None, historical=False):
        """传统预测方法（降级使用）"""
        hs = self.TEAM_STRENGTH.get(home_team, self._default_strength(home_team))
        aws = self.TEAM_STRENGTH.get(away_team, self._default_strength(away_team))
        hs = self.TEAM_STRENGTH.get(home_team, self._default_strength(home_team))
        aws = self.TEAM_STRENGTH.get(away_team, self._default_strength(away_team))
        # 数据驱动修正：根据近期实际战绩调整实力评分
        hs = self._get_real_strength(home_team, hs)
        aws = self._get_real_strength(away_team, aws)
        # 联赛排名修正 (auto_data_service + team_data_service)
        home_injury_impact = 0
        away_injury_impact = 0
        try:
            from services.team_data_service import get_standing_adjustment
            hs += get_standing_adjustment(home_team, league)
            aws += get_standing_adjustment(away_team, league)
        except:
            pass
        try:
            from services.auto_data_service import load_latest_data
            injuries = load_latest_data('injuries')
            if injuries and injuries.get('data'):
                inj_data = injuries['data']
                home_en = home_team  # 中文队名暂用
                away_en = away_team
                if home_en in inj_data:
                    home_injury_impact = min(len(inj_data[home_en]) * 2, 8)
                if away_en in inj_data:
                    away_injury_impact = min(len(inj_data[away_en]) * 2, 8)
            hs -= home_injury_impact
            aws -= away_injury_impact
        except:
            pass
        home_adj = hs + self.HOME_ADVANTAGE
        diff = home_adj - aws

        # === 1. 实力维度 (35%) ===
        strength_probs = self._strength_probability(diff)

        # === 2. 状态维度 (20%) ===
        home_form = self._get_form(home_team)
        away_form = self._get_form(away_team)
        form_probs = self._form_probability(home_form, away_form)

        # === 3. 交锋维度 (15%) ===
        h2h = self._calc_h2h(home_team, away_team, hs, aws)
        h2h_probs = self._h2h_probability(h2h, hs, aws)

        # === 4. 赔率维度 (14%) ===
        odds = self._calc_odds(diff, match_id, home_team, away_team, historical=historical)
        odds_probs = odds['probabilities']

        # === 5. 盘口趋势 (10%) ===
        market = self._market_trend(diff)
        market_probs = market['probabilities']

        # === 6. 外围预测 (10%) ===
        ext = _try_fetch_forebet(home_team, away_team)
        if ext.get('prediction') == 'home':
            ext_probs = {'home': 0.50, 'draw': 0.28, 'away': 0.22}
        elif ext.get('prediction') == 'draw':
            ext_probs = {'home': 0.30, 'draw': 0.45, 'away': 0.25}
        elif ext.get('prediction') == 'away':
            ext_probs = {'home': 0.22, 'draw': 0.28, 'away': 0.50}
        else:
            ext_probs = {'home': 0.40, 'draw': 0.30, 'away': 0.30}

        # === 7. 新闻因素 (10%) ===
        news = _get_news_factors(home_team, away_team, hs, aws)
        morale_diff = news['home_morale'] - news['away_morale']
        news_probs = {'home': 0.38 + morale_diff * 0.03, 'draw': 0.32, 'away': 0.30 - morale_diff * 0.03}
        # 天气影响
        if news['weather_impact'] < 0:
            # 恶劣天气增加平局概率
            news_probs['draw'] += abs(news['weather_impact']) * 0.02
            news_probs['home'] -= abs(news['weather_impact']) * 0.01
            news_probs['away'] -= abs(news['weather_impact']) * 0.01

        # === 8. 主客场表现 (8%) ===
        home_away_diff = (hs - aws) * 0.3  # 主场优势放大
        if home_away_diff > 5:
            hap = {'home': 0.50, 'draw': 0.28, 'away': 0.22}
        elif home_away_diff < -5:
            hap = {'home': 0.22, 'draw': 0.28, 'away': 0.50}
        else:
            hap = {'home': 0.40, 'draw': 0.32, 'away': 0.28}

        # === 9. 进球效率 (8%) ===
        h_goals = hs / 100 * 1.8  # 场均进球
        a_goals = aws / 100 * 1.8
        gd = h_goals - a_goals
        if gd > 0.5:
            gap = {'home': 0.48, 'draw': 0.28, 'away': 0.24}
        elif gd < -0.5:
            gap = {'home': 0.24, 'draw': 0.28, 'away': 0.48}
        else:
            gap = {'home': 0.38, 'draw': 0.34, 'away': 0.28}

        # === 10. 赛程体能 (7%) ===
        # 实力强的队多线作战（欧冠+联赛），体能略受影响
        if hs > 85:
            fatigue_h = -1  # 强队多线作战，体能稍差
        elif hs < 70:
            fatigue_h = 1   # 弱队专注联赛，体能好
        else:
            fatigue_h = 0
        fatigue_a = -1 if aws > 85 else (1 if aws < 70 else 0)
        fd2 = fatigue_h - fatigue_a
        if fd2 > 0:
            fp = {'home': 0.42, 'draw': 0.32, 'away': 0.26}
        elif fd2 < 0:
            fp = {'home': 0.26, 'draw': 0.32, 'away': 0.42}
        else:
            fp = {'home': 0.36, 'draw': 0.34, 'away': 0.30}

        # 外部预测权重（根据共识程度动态调整）
        try:
            src_count = int(ext.get('sources', '0').split()[0])
        except:
            src_count = 0
        if ext.get('available') and src_count >= 5:
            ext_weight = 0.35  # 5+源高度共识
        elif ext.get('available') and src_count >= 3:
            ext_weight = 0.28  # 3-4源共识
        elif ext.get('available') and src_count >= 1:
            ext_weight = 0.20  # 1-2源参考
        else:
            ext_weight = 0.0

        base_total = 1.0 - ext_weight
        # 动态权重: 状态和赔率比静态实力更重要
        # [实力, 状态, 交锋, 赔率, 盘口, 新闻, 主客场, 进球, 体能]
        w = [0.18, 0.22, 0.09, 0.16, 0.08, 0.08, 0.07, 0.07, 0.05]
        w_sum = sum(w)
        w = [x / w_sum * base_total for x in w]

        home_p = (strength_probs['home'] * w[0] + form_probs['home'] * w[1] +
                  h2h_probs['home'] * w[2] + odds_probs['home'] * w[3] +
                  market_probs['home'] * w[4] + news_probs['home'] * w[5] +
                  hap['home'] * w[6] + gap['home'] * w[7] + fp['home'] * w[8])
        draw_p = (strength_probs['draw'] * w[0] + form_probs['draw'] * w[1] +
                  h2h_probs['draw'] * w[2] + odds_probs['draw'] * w[3] +
                  market_probs['draw'] * w[4] + news_probs['draw'] * w[5] +
                  hap['draw'] * w[6] + gap['draw'] * w[7] + fp['draw'] * w[8])
        away_p = (strength_probs['away'] * w[0] + form_probs['away'] * w[1] +
                  h2h_probs['away'] * w[2] + odds_probs['away'] * w[3] +
                  market_probs['away'] * w[4] + news_probs['away'] * w[5] +
                  hap['away'] * w[6] + gap['away'] * w[7] + fp['away'] * w[8])

        if ext_weight > 0:
            home_p += ext_probs['home'] * ext_weight
            draw_p += ext_probs['draw'] * ext_weight
            away_p += ext_probs['away'] * ext_weight

        # === 凯利指数修正 (市场预期信号) ===
        kelly = odds.get('kelly', {})
        if kelly and odds.get('real_odds_available'):
            kh = kelly.get('home', 33)
            kd = kelly.get('draw', 33)
            ka = kelly.get('away', 33)
            # 凯利指数反映市场赔率隐含概率，偏离均衡说明市场有明确预期
            kelly_home_bias = (kh - 33) / 100  # 偏离均衡的程度
            kelly_draw_bias = (kd - 33) / 100
            kelly_away_bias = (ka - 33) / 100
            # 凯利权重5%（仅修正，不起主导作用）
            kelly_weight = 0.05
            home_p += kelly_home_bias * kelly_weight
            draw_p += kelly_draw_bias * kelly_weight
            away_p += kelly_away_bias * kelly_weight

        # === 平台共识修正：外部数据源共识大幅影响最终判断 ===
        raw_total = home_p + draw_p + away_p
        raw_probs = {'home': home_p/raw_total*100, 'draw': draw_p/raw_total*100, 'away': away_p/raw_total*100}
        platforms_pre = self._platform_predictions(raw_probs, diff, hs, aws, match_id, home_team, away_team)
        pv = self._count_platform_votes(platforms_pre, raw_probs)
        plat_votes = pv['votes']
        ext_total = sum(plat_votes[k] for k in ['home','draw','away'])

        if ext_total >= 3:
            # 有足够的外部数据才进行共识修正
            ext_home_pct = plat_votes['home'] / ext_total
            ext_draw_pct = plat_votes['draw'] / ext_total
            ext_away_pct = plat_votes['away'] / ext_total

            # 外部高度一致(>=67%) → 大幅加权
            if ext_home_pct >= 0.67:
                home_p += 0.08; draw_p -= 0.04; away_p -= 0.04
            elif ext_draw_pct >= 0.67:
                draw_p += 0.08; home_p -= 0.04; away_p -= 0.04
            elif ext_away_pct >= 0.67:
                away_p += 0.08; home_p -= 0.04; draw_p -= 0.04
            # 外部相对一致(>=50%) → 适度加权
            elif ext_home_pct >= 0.5:
                home_p += 0.04; draw_p -= 0.02; away_p -= 0.02
            elif ext_draw_pct >= 0.5:
                draw_p += 0.04; home_p -= 0.02; away_p -= 0.02
            elif ext_away_pct >= 0.5:
                away_p += 0.04; home_p -= 0.02; draw_p -= 0.02

        # === 实力差不足12分时的修正：大力增加平局权重 ===
        if abs(diff) <= 12:
            closeness = (12 - abs(diff)) / 12  # diff=0时=1, diff=12时=0
            draw_boost = closeness * 0.10  # 最多+10%
            draw_p += draw_boost
            home_p -= draw_boost * 0.5
            away_p -= draw_boost * 0.5

        # === 赔率平衡检测: 三项赔率接近 → 市场认为是平局 ===
        if odds.get('real_odds_available') and odds.get('opening'):
            op = odds['opening']
            # 计算赔率离散度: 三项赔率越接近，平局概率越高
            vals = [op['home'], op['draw'], op['away']]
            if all(v > 0 for v in vals):
                avg_val = sum(vals) / 3
                spread = max(vals) - min(vals)
                if spread < 0.8:  # 赔率差距小於0.8，说明市场认为势均力敌
                    draw_p += 0.05
                    home_p -= 0.025
                    away_p -= 0.025

        # 归一化
        total = home_p + draw_p + away_p
        probs = {
            'home': round(home_p / total * 100, 1),
            'draw': round(draw_p / total * 100, 1),
            'away': round(away_p / total * 100, 1),
        }

        # === 外部共识覆盖：外部数据高度一致时，覆盖模型判断 ===
        ext_votes = pv['votes']
        ext_total = sum(ext_votes[k] for k in ['home','draw','away'])
        if ext_total >= 2:
            ext_consensus_key = max(['home','draw','away'], key=lambda k: ext_votes[k])
            ext_consensus_pct = ext_votes[ext_consensus_key] / ext_total
            if ext_consensus_pct >= 0.67 and ext_consensus_key != 'draw':
                # 外部高度一致指向胜负，且模型因为实力接近选了平局 → 听外部的
                if abs(diff) <= 6 and probs['draw'] >= probs[ext_consensus_key] - 5:
                    # 强制指向外部共识方向
                    boost = 0.06
                    probs = {
                        'home': probs['home'] + (boost if ext_consensus_key == 'home' else -boost/2),
                        'draw': probs['draw'] - boost/2,
                        'away': probs['away'] + (boost if ext_consensus_key == 'away' else -boost/2),
                    }
                    # 重新归一化
                    t = sum(probs.values())
                    probs = {k: round(v/t*100, 1) for k, v in probs.items()}

        # 选择最高概率 — 尊重数据: 主场优势真实存在, 平局不应强制
        sorted_items = sorted(probs.items(), key=lambda x: x[1], reverse=True)
        first_key, first_val = sorted_items[0]
        second_key, second_val = sorted_items[1]
        prob_gap = first_val - second_val
        is_close = prob_gap < 8

        # 外部共识信号
        ext_votes = pv['votes']
        ext_total = sum(ext_votes[k] for k in ['home','draw','away'])
        ext_agree = ext_total >= 2 and max(ext_votes['home'], ext_votes['draw'], ext_votes['away']) >= ext_total * 0.67

        # 外部共识最强信号
        ext_consensus_key = max(['home','draw','away'], key=lambda k: ext_votes.get(k, 0)) if ext_total >= 2 else None
        ext_consensus_pct = ext_votes.get(ext_consensus_key, 0) / ext_total if ext_total >= 2 else 0

        # ── 平局优化 ──
        # 平局在足球中约占27%，但之前模型几乎不预测平局
        # 新逻辑：实力接近时提高平局优先级
        if probs['draw'] >= probs['home'] and probs['draw'] >= probs['away'] and probs['draw'] >= 32:
            best = 'draw'  # 平局最高且>=32% → 选平
        elif is_close and probs['draw'] >= 30 and probs['draw'] >= first_val - 5:
            best = 'draw'  # 实力接近+平局概率不低 → 谨慎选平
        elif ext_consensus_pct >= 0.67:
            best = ext_consensus_key  # 外部高度一致
        elif ext_consensus_pct >= 0.5 and probs[ext_consensus_key] >= first_val - 3:
            best = ext_consensus_key
        elif first_key == 'home' and prob_gap > 6:
            best = 'home'  # 主胜明显领先
        elif first_key == 'home' and probs['draw'] >= 30:
            best = 'draw'  # 主胜微弱领先+平局有戏 → 选平
        elif first_key == 'away' and prob_gap > 8:
            best = 'away'  # 客胜明显领先
        elif first_key == 'away' and probs['draw'] >= 28:
            best = 'draw'  # 客胜微弱领先 → 平局更可能
        elif first_key == 'away' and probs['home'] >= first_val - 3:
            best = 'home'
        else:
            best = first_key

        # 置信度 — 更保守的计算，避免虚高
        margin_bonus = min(prob_gap * 0.4, 8)
        gap_bonus = min(abs(diff) * 0.2, 5)
        close_penalty = -6 if is_close else 0
        conf = probs[best] + margin_bonus + gap_bonus + close_penalty
        conf = min(78, max(28, conf))
        if abs(diff) <= 4 and is_close:
            conf = min(conf, 52)
        elif abs(diff) <= 8 and is_close:
            conf = min(conf, 58)

        result_names = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
        if conf >= 65:
            level = '高'
        elif conf >= 55:
            level = '中'
        else:
            level = '低'

        # 预测比分
        score = self._predict_score(best, diff)

        # 各平台预测（优先真实博彩公司数据）
        platforms = self._platform_predictions(probs, diff, hs, aws, match_id, home_team, away_team)

        # 分析摘要
        summary = self._build_summary(home_team, away_team, hs, aws, diff, probs, h2h, odds, home_form, away_form, news, ext, is_close, prob_gap)

        return {
            'match': {'home_team': home_team, 'away_team': away_team, 'league': league},
            'prediction': {
                'prediction': best,
                'prediction_name': result_names[best],
                'confidence': conf,
                'probabilities': probs,
                'confidence_level': level,
                'predicted_score': score,
                'model_type': 'comprehensive_multi_dimension',
                'is_close_match': is_close,
                'prob_gap': round(prob_gap, 1),
            },
            'platform_predictions': platforms,
            # 多平台投票统计
            'platform_votes': self._count_platform_votes(platforms, probs),
            'odds_analysis': {
                'opening_odds': odds['opening'],
                'live_odds': odds['live'],
                'kelly_index': odds['kelly'],
                'trend': odds['trend'],
                'real_odds_available': odds['real_odds_available'],
                'odds_change_signal': odds.get('odds_change_signal'),
                'timeline': odds.get('timeline', []),
                'sporttery_timeline': odds.get('sporttery_timeline', []),
                'intl_timeline': odds.get('intl_timeline', []),
                'probabilities': probs,
            },
            'team_analysis': {
                'home': {
                    'name': home_team,
                    'strength': hs,
                    'form': home_form,
                    'win_rate': round(30 + (hs - 60) * 0.7, 1),
                    'player_value': _get_player_value_info(home_team),
                },
                'away': {
                    'name': away_team,
                    'strength': aws,
                    'form': away_form,
                    'win_rate': round(30 + (aws - 60) * 0.7, 1),
                    'player_value': _get_player_value_info(away_team),
                },
            },
            'h2h_analysis': h2h,
            'news_analysis': {
                'home': {
                    'injuries': len(news['home_injuries']) + home_injury_impact,
                    'injury_detail': news['home_injuries'],
                    'suspensions': news['home_suspensions'],
                    'morale': news['home_morale'],
                },
                'away': {
                    'injuries': len(news['away_injuries']) + away_injury_impact,
                    'injury_detail': news['away_injuries'],
                    'suspensions': news['away_suspensions'],
                    'morale': news['away_morale'],
                },
                'weather': news['weather'],
                'weather_impact': news['weather_impact'],
                'external_source': ext,
                'injury_data': {
                    'home_impact': home_injury_impact,
                    'away_impact': away_injury_impact,
                },
            },
            'analysis_summary': summary,
        }

    # ── 各维度计算 ──────────────────────────────────────────

    def _strength_probability(self, diff):
        """实力维度 - 实力接近时平局概率最高"""
        if abs(diff) < 3:
            return {'home': 0.34, 'draw': 0.38, 'away': 0.28}
        elif abs(diff) < 6:
            if diff > 0:
                return {'home': 0.38, 'draw': 0.34, 'away': 0.28}
            else:
                return {'home': 0.28, 'draw': 0.34, 'away': 0.38}
        elif abs(diff) < 12:
            r = (abs(diff) - 6) / 6
            if diff > 0:
                return {'home': 0.42 + r * 0.16, 'draw': 0.32 - r * 0.06, 'away': 0.26 - r * 0.10}
            else:
                return {'home': 0.26 - r * 0.10, 'draw': 0.32 - r * 0.06, 'away': 0.42 + r * 0.16}
        else:
            r = min(1.0, (abs(diff) - 12) / 15)
            if diff > 0:
                return {'home': 0.58 + r * 0.07, 'draw': 0.26 - r * 0.05, 'away': 0.16 - r * 0.02}
            else:
                return {'home': 0.16 - r * 0.02, 'draw': 0.26 - r * 0.05, 'away': 0.58 + r * 0.07}

    def _get_form(self, team_name):
        """近期状态 — 优先真实数据，无数据时用实力估算"""
        real = _get_real_form(team_name)
        if real is not None and real['results']:
            return real
        # 无真实数据时的兜底估算
        strength = self.TEAM_STRENGTH.get(team_name, self._default_strength(team_name))
        if strength >= 80:
            return {'results': ['W', 'W', 'D', 'W', 'L'], 'pts': 10}
        elif strength >= 70:
            return {'results': ['D', 'W', 'L', 'W', 'D'], 'pts': 8}
        elif strength >= 60:
            return {'results': ['L', 'D', 'W', 'L', 'W'], 'pts': 5}
        else:
            return {'results': ['L', 'D', 'L', 'W', 'L'], 'pts': 4}

    def _form_probability(self, home_form, away_form):
        """状态维度"""
        hp = home_form['pts']
        ap = away_form['pts']
        fd = hp - ap
        if fd > 4:
            return {'home': 0.55, 'draw': 0.25, 'away': 0.20}
        elif fd > 1:
            return {'home': 0.45, 'draw': 0.30, 'away': 0.25}
        elif fd < -4:
            return {'home': 0.20, 'draw': 0.25, 'away': 0.55}
        elif fd < -1:
            return {'home': 0.25, 'draw': 0.30, 'away': 0.45}
        else:
            return {'home': 0.38, 'draw': 0.34, 'away': 0.28}

    def _calc_h2h(self, home, away, hs, aws):
        """历史交锋 — 优先真实数据，无数据时用实力差估算"""
        real = _get_real_h2h(home, away)
        if real is not None:
            return real
        # 无真实数据时的兜底估算
        sd = hs - aws
        total = 8
        if sd > 12:
            hw, aw = 5, 1
        elif sd > 5:
            hw, aw = 4, 2
        elif sd < -12:
            hw, aw = 1, 5
        elif sd < -5:
            hw, aw = 2, 4
        else:
            hw, aw = 3, 3
        return {'total': total, 'home_wins': hw, 'draws': total - hw - aw, 'away_wins': aw}

    def _h2h_probability(self, h2h, hs, aws):
        """交锋维度"""
        t = h2h['total']
        if t == 0:
            return {'home': 0.40, 'draw': 0.30, 'away': 0.30}
        hw_r = h2h['home_wins'] / t
        aw_r = h2h['away_wins'] / t
        dr = h2h['draws'] / t
        # 主队交锋优势时更偏向主胜
        if hw_r > 0.5:
            return {'home': 0.55, 'draw': 0.25, 'away': 0.20}
        elif aw_r > 0.5:
            return {'home': 0.20, 'draw': 0.25, 'away': 0.55}
        elif hw_r > aw_r:
            return {'home': 0.45, 'draw': 0.30, 'away': 0.25}
        elif aw_r > hw_r:
            return {'home': 0.25, 'draw': 0.30, 'away': 0.45}
        return {'home': 0.38, 'draw': 0.32, 'away': 0.30}

    def _fetch_real_odds(self, match_id, home_team, away_team):
        """从数据库获取真实赔率数据，返回赔率变化趋势 + 时间线"""
        result = {
            'found': False, 'opening': None, 'live': None,
            'changes': {}, 'trend': 'stable',
            'timeline': [],           # 所有赔率变化时间线
            'sporttery_timeline': [], # 体彩官方赔率变化
            'intl_timeline': [],      # 国际博彩公司赔率变化
        }
        try:
            from app.db_helper import db_cursor
            with db_cursor() as cur:
                # 查询该比赛的赔率
                if match_id:
                    cur.execute(
                        'SELECT bookmaker, home_odds, draw_odds, away_odds, is_opening, created_at '
                        'FROM odds WHERE match_id=%s ORDER BY created_at', (match_id,))
                else:
                    cur.execute(
                        'SELECT o.match_id, o.bookmaker, o.home_odds, o.draw_odds, o.away_odds, '
                        'o.is_opening, o.created_at '
                        'FROM odds o JOIN matches m ON o.match_id=m.match_id '
                        'WHERE m.home_team_name=%s AND m.away_team_name=%s '
                        'ORDER BY o.created_at',
                        (home_team, away_team))
                rows = cur.fetchall()

            if not rows:
                return result

            result['found'] = True
            # 按博彩公司分组
            from collections import defaultdict
            bookmakers = defaultdict(list)
            for row in rows:
                if match_id:
                    bm, ho, do, ao, is_op, ct = row
                else:
                    _, bm, ho, do, ao, is_op, ct = row
                bookmakers[bm].append({
                    'home': float(ho) if ho else 0,
                    'draw': float(do) if do else 0,
                    'away': float(ao) if ao else 0,
                    'is_opening': bool(is_op),
                    'time': str(ct) if ct else ''
                })

            # 取所有博彩公司开盘的平均值作为 opening
            all_openings = {'home': [], 'draw': [], 'away': []}
            all_latest = {'home': [], 'draw': [], 'away': []}
            changes_list = []

            for bm, records in bookmakers.items():
                if len(records) < 1:
                    continue
                opening_rec = records[0]
                latest_rec = records[-1]

                # 分别收集开盘赔率和最新赔率
                for key in ['home', 'draw', 'away']:
                    if opening_rec[key] > 0:
                        all_openings[key].append(opening_rec[key])
                    if latest_rec[key] > 0:
                        all_latest[key].append(latest_rec[key])

                # 计算每家公司变化
                if len(records) >= 2:
                    ch = {
                        'bookmaker': bm,
                        'home_change': round(latest_rec['home'] - opening_rec['home'], 3),
                        'draw_change': round(latest_rec['draw'] - opening_rec['draw'], 3),
                        'away_change': round(latest_rec['away'] - opening_rec['away'], 3),
                    }
                    changes_list.append(ch)

            # 计算平均值
            def avg(lst):
                return round(sum(lst) / len(lst), 3) if lst else 0

            result['opening'] = {
                'home': avg(all_openings['home']) or 2.50,
                'draw': avg(all_openings['draw']) or 3.20,
                'away': avg(all_openings['away']) or 2.80
            }
            result['live'] = {
                'home': avg(all_latest['home']) or result['opening']['home'],
                'draw': avg(all_latest['draw']) or result['opening']['draw'],
                'away': avg(all_latest['away']) or result['opening']['away']
            }

            # 构建赔率变化时间线（每个bookmaker的时间序列）
            import collections as _col
            timeline_all = []
            for bm, records in bookmakers.items():
                if len(records) >= 2:
                    # 按时序排列
                    sorted_recs = sorted(records, key=lambda r: r['time'])
                    # 为每个bookmaker生成变化节点
                    prev = None
                    for rec in sorted_recs:
                        if prev is None:
                            prev = rec
                            continue
                        # 检测变化
                        h_ch = round(rec['home'] - prev['home'], 3)
                        d_ch = round(rec['draw'] - prev['draw'], 3)
                        a_ch = round(rec['away'] - prev['away'], 3)
                        if abs(h_ch) > 0.005 or abs(d_ch) > 0.005 or abs(a_ch) > 0.005:
                            node = {
                                'bookmaker': bm,
                                'time': rec['time'][:16] if rec['time'] else '',
                                'home': rec['home'],
                                'draw': rec['draw'],
                                'away': rec['away'],
                                'home_change': h_ch,
                                'draw_change': d_ch,
                                'away_change': a_ch,
                            }
                            timeline_all.append(node)
                        prev = rec
                # 开盘节点
                first = sorted(records, key=lambda r: r['time'])[0]
                timeline_all.append({
                    'bookmaker': bm,
                    'time': first['time'][:16] if first['time'] else '',
                    'home': first['home'],
                    'draw': first['draw'],
                    'away': first['away'],
                    'home_change': 0,
                    'draw_change': 0,
                    'away_change': 0,
                    'is_opening': True,
                })

            # 按时序排序
            timeline_all.sort(key=lambda n: n['time'])
            result['timeline'] = timeline_all

            # 分离体彩和国际赔率
            result['sporttery_timeline'] = [n for n in timeline_all if 'sporttery' in n.get('bookmaker', '').lower()]
            result['intl_timeline'] = [n for n in timeline_all if 'sporttery' not in n.get('bookmaker', '').lower()]

            # 汇总变化趋势
            if changes_list:
                avg_home_ch = sum(c['home_change'] for c in changes_list) / len(changes_list)
                avg_draw_ch = sum(c['draw_change'] for c in changes_list) / len(changes_list)
                avg_away_ch = sum(c['away_change'] for c in changes_list) / len(changes_list)

                # 找最新的更新时间
                all_times = []
                for records in bookmakers.values():
                    for rec in records:
                        if rec['time']:
                            all_times.append(rec['time'])
                last_update = max(all_times) if all_times else ''

                result['changes'] = {
                    'home': round(avg_home_ch, 3),
                    'draw': round(avg_draw_ch, 3),
                    'away': round(avg_away_ch, 3),
                    'details': changes_list,
                    'consensus': len(changes_list),
                    'last_update': last_update
                }

                # 判断趋势（阈值为 0.1 即变化超过 0.1 视为显著）
                drops = []
                if avg_home_ch < -0.1:
                    drops.append('home')
                if avg_draw_ch < -0.1:
                    drops.append('draw')
                if avg_away_ch < -0.1:
                    drops.append('away')

                if len(drops) >= 2:
                    result['trend'] = 'mixed_dropping'
                elif len(drops) == 1:
                    result['trend'] = drops[0] + '_dropping'
                else:
                    result['trend'] = 'stable'

        except Exception as e:
            logger.warning(f'Real odds fetch failed: {e}')

        return result

    def _calc_odds(self, diff, match_id=None, home_team='', away_team='', historical=False):
        """赔率分析 - 优先使用真实赔率，检测赔率变化趋势，回退到理论赔率
        historical=True时只用开盘赔率(不作变动修正)，避免查历史时用终盘数据
        """
        # 尝试获取真实赔率
        real = self._fetch_real_odds(match_id, home_team, away_team)

        # === 先计算基础概率（从实力差） ===
        if abs(diff) < 4:
            hp_base, dp_base, ap_base = 0.40, 0.32, 0.28
        elif abs(diff) < 10:
            r = (abs(diff) - 4) / 6
            if diff > 0:
                hp_base, dp_base, ap_base = 0.44 + r * 0.16, 0.30 - r * 0.04, 0.26 - r * 0.12
            else:
                hp_base, dp_base, ap_base = 0.26 - r * 0.12, 0.30 - r * 0.04, 0.44 + r * 0.16
        else:
            r = min(1.0, (abs(diff) - 10) / 15)
            if diff > 0:
                hp_base, dp_base, ap_base = 0.60 + r * 0.07, 0.26 - r * 0.05, 0.14 - r * 0.02
            else:
                hp_base, dp_base, ap_base = 0.14 - r * 0.02, 0.26 - r * 0.05, 0.60 + r * 0.07

        hp, dp, ap = hp_base, dp_base, ap_base
        odds_change_signal = None

        # === 如果有真实赔率，用它来修正概率 ===
        if real['found'] and real['live'] and real['live']['home'] > 0:
            live = real['live']
            opening = real['opening']
            # 从真实赔率反推概率
            margin = 1.0 / live['home'] + 1.0 / live['draw'] + 1.0 / live['away']
            hp_real = round(1.0 / live['home'] / margin, 4)
            dp_real = round(1.0 / live['draw'] / margin, 4)
            ap_real = round(1.0 / live['away'] / margin, 4)

            if historical:
                # 历史模式: 只用开盘赔率推算概率（预测当时的信息），不参考终盘
                open_margin = 1.0 / opening['home'] + 1.0 / opening['draw'] + 1.0 / opening['away']
                hp_open = round(1.0 / opening['home'] / open_margin, 4)
                dp_open = round(1.0 / opening['draw'] / open_margin, 4)
                ap_open = round(1.0 / opening['away'] / open_margin, 4)
                # 开盘赔率权重20%（谨慎参考），模型80%
                hp = hp_base * 0.80 + hp_open * 0.20
                dp = dp_base * 0.80 + dp_open * 0.20
                ap = ap_base * 0.80 + ap_open * 0.20
            else:
                # 实时模式: 融合市场信号 —— 赔率是真金白银，应受尊重
                # 检测赔率明确指向: 最低赔率方向 = 市场共识
                min_odds = min(live['home'], live['draw'], live['away'])
                max_odds = max(live['home'], live['draw'], live['away'])
                odds_spread = max_odds - min_odds  # 赔率差: 越大越明确

                if min_odds < 1.5 and odds_spread > 1.5:
                    # 市场极度明确 (如主1.3 客6.0) → 高度信任市场
                    odds_weight = 0.65
                elif min_odds < 1.8 and odds_spread > 1.0:
                    # 市场比较明确 (如主1.6 客4.0) → 信任市场
                    odds_weight = 0.50
                elif min_odds < 2.0 and odds_spread > 0.6:
                    # 市场有一定倾向 → 适度信任
                    odds_weight = 0.40
                elif odds_spread < 0.5:
                    # 三项赔率接近 → 市场也看不清，降低赔率权重
                    odds_weight = 0.15
                else:
                    gap_factor = min(1.0, abs(diff) / 20.0)
                    odds_weight = 0.20 + gap_factor * 0.10  # 20%~30%

                model_weight = 1.0 - odds_weight
                hp = hp_base * model_weight + hp_real * odds_weight
                dp = dp_base * model_weight + dp_real * odds_weight
                ap = ap_base * model_weight + ap_real * odds_weight

            # === 赔率变化检测（核心：赔率下降 → 预测跟着调整）===
            if real.get('changes') and real['changes'].get('consensus', 0) >= 1:
                ch = real['changes']
                consensus = ch['consensus']

                # 赔率变化截止时间
                last_update = ch.get('last_update', '')
                time_suffix = f' (截止{last_update})' if last_update else ''

                # 赔率下降超过 0.1 视为显著信号
                home_drop = ch['home'] < -0.1
                draw_drop = ch['draw'] < -0.1
                away_drop = ch['away'] < -0.1

                # 置信度 = 价格变动幅度 × 博彩公司共识度
                if home_drop:
                    boost = min(0.12, abs(ch['home']) * 0.5) * min(consensus, 3) / 3
                    hp += boost
                    dp -= boost * 0.6
                    ap -= boost * 0.4
                    odds_change_signal = f'赔率下降信号: 主胜赔↓{abs(ch["home"]):.2f}({consensus}家共识){time_suffix}'

                if draw_drop:
                    boost = min(0.10, abs(ch['draw']) * 0.4) * min(consensus, 3) / 3
                    dp += boost
                    hp -= boost * 0.5
                    ap -= boost * 0.5
                    signal = f'赔率下降信号: 平局赔↓{abs(ch["draw"]):.2f}({consensus}家共识){time_suffix}'
                    odds_change_signal = signal if not odds_change_signal else odds_change_signal + ' | ' + signal

                if away_drop:
                    boost = min(0.12, abs(ch['away']) * 0.5) * min(consensus, 3) / 3
                    ap += boost
                    hp -= boost * 0.4
                    dp -= boost * 0.6
                    signal = f'赔率下降信号: 客胜赔↓{abs(ch["away"]):.2f}({consensus}家共识){time_suffix}'
                    odds_change_signal = signal if not odds_change_signal else odds_change_signal + ' | ' + signal

                # 如果没有任何降赔，但有升赔，适度削弱对应概率
                if not (home_drop or draw_drop or away_drop):
                    if ch['home'] > 0.15:
                        hp -= min(0.05, ch['home'] * 0.15)
                    if ch['away'] > 0.15:
                        ap -= min(0.05, ch['away'] * 0.15)

            # 归一化
            total = hp + dp + ap
            hp, dp, ap = hp / total, dp / total, ap / total

            opening = real['opening']
            kelly_base = live
        else:
            # === 无真实赔率，使用理论赔率（旧逻辑） ===
            margin = 1.08
            opening = {
                'home': round(margin / hp, 2),
                'draw': round(margin / dp, 2),
                'away': round(margin / ap, 2),
            }
            live = {
                'home': round(opening['home'] + (0.05 if diff > 8 else -0.03 if diff < -8 else 0), 2),
                'draw': round(opening['draw'] + 0.02, 2),
                'away': round(opening['away'] + (-0.05 if diff > 8 else 0.03 if diff < -8 else 0), 2),
            }
            kelly_base = live

        # 凯利指数
        kelly = {}
        try:
            t = 1 / kelly_base['home'] + 1 / kelly_base['draw'] + 1 / kelly_base['away']
            kelly = {
                'home': round((1 / kelly_base['home']) / t * 100, 1),
                'draw': round((1 / kelly_base['draw']) / t * 100, 1),
                'away': round((1 / kelly_base['away']) / t * 100, 1),
            }
        except:
            kelly = {'home': 33.3, 'draw': 33.3, 'away': 33.3}

        return {
            'opening': opening, 'live': live, 'kelly': kelly,
            'probabilities': {'home': round(hp, 4), 'draw': round(dp, 4), 'away': round(ap, 4)},
            'odds_change_signal': odds_change_signal,
            'trend': real.get('trend', 'stable') if real['found'] else 'synthetic',
            'real_odds_available': real['found'],
        }

    def _market_trend(self, diff):
        """盘口趋势分析"""
        if diff > 12:
            trend = 'home_dropping'
            probs = {'home': 0.60, 'draw': 0.25, 'away': 0.15}
        elif diff > 5:
            trend = 'home_slight'
            probs = {'home': 0.48, 'draw': 0.30, 'away': 0.22}
        elif diff < -12:
            trend = 'away_dropping'
            probs = {'home': 0.15, 'draw': 0.25, 'away': 0.60}
        elif diff < -5:
            trend = 'away_slight'
            probs = {'home': 0.22, 'draw': 0.30, 'away': 0.48}
        else:
            trend = 'stable'
            probs = {'home': 0.38, 'draw': 0.32, 'away': 0.30}
        return {'trend': trend, 'probabilities': probs}

    def _predict_score(self, prediction, diff):
        """预测比分 — 确保比分与预测类型一致"""
        if prediction == 'home':
            if diff > 18:
                return '3-0'
            elif diff > 10:
                return '2-0'
            else:
                return '2-1'
        elif prediction == 'draw':
            return '1-1'
        elif prediction == 'away':
            if diff < -18:
                return '0-3'
            elif diff < -10:
                return '0-2'
            else:
                return '1-2'
        else:
            return '1-1'

    def _platform_predictions(self, probs, diff, hs, aws, match_id=None, home_team='', away_team='', league_name=''):
        """多平台预测 — 真实博彩赔率 + 真实国际预测源"""
        try:
            from services.multi_source_fetcher import (
                get_real_bookmaker_predictions, get_real_external_predictions
            )
            bookmaker_plats = get_real_bookmaker_predictions(match_id, home_team, away_team, league_name)
            external_plats = get_real_external_predictions(home_team, away_team)
            if bookmaker_plats or external_plats:
                return bookmaker_plats + external_plats
        except Exception as e:
            logger.warning(f'Multi-source fetch failed: {e}')
        # Fallback
        bookmaker_plats = self._get_bookmaker_predictions(match_id, home_team, away_team) or []
        external_plats = self._get_external_source_predictions(home_team, away_team)
        return bookmaker_plats + external_plats

    def _get_bookmaker_predictions(self, match_id, home_team, away_team):
        """从真实赔率数据库获取各博彩公司的预测"""
        try:
            import pymysql

            # 先从DB获取
            from app.db_helper import db_cursor
            with db_cursor() as cur:
                if match_id:
                    cur.execute('SELECT bookmaker, home_odds, draw_odds, away_odds, is_opening, created_at FROM odds WHERE match_id=%s ORDER BY created_at DESC', (match_id,))
                else:
                    cur.execute('''SELECT o.bookmaker, o.home_odds, o.draw_odds, o.away_odds, o.is_opening, o.created_at
                        FROM odds o JOIN matches m ON o.match_id=m.match_id
                        WHERE m.home_team_name=%s AND m.away_team_name=%s ORDER BY o.created_at DESC''', (home_team, away_team))
                rows = cur.fetchall()

            from collections import defaultdict
            bookmakers = defaultdict(list)
            for bm, ho, do, ao, is_op, ct in (rows or []):
                bookmakers[bm].append({'home': float(ho), 'draw': float(do), 'away': float(ao), 'is_opening': bool(is_op)})

            if not bookmakers:
                return None

            bm_names = {
                'sporttery_cn': '竞彩官方', 'bet365_cn': 'Bet365', 'bet365': 'Bet365',
                'william_hill': '威廉希尔', 'ladbrokes': '立博',
                'betfair': '必发交易所', 'pinnacle': '平博',
                'crown': '皇冠', 'macau': '澳门彩票',
                'bwin': 'bwin', 'interwetten': 'Interwetten',
            }
            bm_styles = {
                'sporttery_cn': '体彩官方赔率', 'bet365_cn': '国际主流赔率',
                'william_hill': '英式赔率体系', 'ladbrokes': '欧洲老牌赔率',
                'betfair': '交易所赔率，反映真实市场', 'pinnacle': '低水精准赔率',
                'crown': '亚洲主流水位', 'macau': '亚洲盘口权威',
                'bwin': '欧洲综合博彩', 'interwetten': '欧洲老牌保守',
            }

            results = []
            for bm, records in bookmakers.items():
                if len(records) < 1:
                    continue
                latest = records[0]
                margin = 1.0/latest['home'] + 1.0/latest['draw'] + 1.0/latest['away']
                hp = round(1.0/latest['home'] / margin * 100, 1)
                dp = round(1.0/latest['draw'] / margin * 100, 1)
                ap = round(1.0/latest['away'] / margin * 100, 1)
                best = max([('home', hp), ('draw', dp), ('away', ap)], key=lambda x: x[1])
                conf = min(75, max(30, best[1] + 5))

                reasons = []
                if latest['home'] < 2.0: reasons.append('主胜低赔，市场看好主队')
                if latest['draw'] < 3.5: reasons.append('平赔偏低，有平局可能')
                if latest['away'] < 2.0: reasons.append('客胜低赔，市场看好客队')
                if abs(latest['home'] - latest['away']) < 0.3: reasons.append('胜负赔率接近，实力均衡')
                if len(records) >= 2:
                    opening = records[-1]
                    if abs(opening['home'] - latest['home']) > 0.1:
                        ch = '↓' if latest['home'] < opening['home'] else '↑'
                        reasons.append(f'主胜赔率变化{ch}{abs(round(opening["home"]-latest["home"],2))}')
                if not reasons: reasons.append('赔率结构分析')

                display_name = bm_names.get(bm, bm.replace('500_', ''))
                results.append({
                    'platform': display_name,
                    'prediction': best[0],
                    'confidence': conf,
                    'style': bm_styles.get(bm, '博彩赔率分析'),
                    'reasons': reasons,
                    'odds': {'home': latest['home'], 'draw': latest['draw'], 'away': latest['away']},
                    'data_source': 'real',
                })

            return results if len(results) >= 1 else None
        except Exception as e:
            logger.warning(f'Bookmaker predictions failed: {e}')
            return None

    def _get_external_source_predictions(self, home_team, away_team):
        """从外部预测数据源获取该场比赛的预测"""
        try:
            from services.external_aggregator import load_all_external_predictions, _translate_team
            all_preds = load_all_external_predictions()
            matches = []
            home_en = _translate_team(home_team)
            away_en = _translate_team(away_team)
            for p in all_preds:
                ph = p.get('home', '').lower().strip()
                pa = p.get('away', '').lower().strip()
                h_match = (home_team in ph or ph in home_team or home_en in ph or ph in home_en)
                a_match = (away_team in pa or pa in away_team or away_en in pa or pa in away_en)
                if h_match and a_match:
                    matches.append(p)
            if not matches:
                return []

            # 去重并转换
            results = []
            seen_sources = set()
            for m in matches[:6]:  # 最多6个外部源
                src = m.get('source', 'unknown')
                if src in seen_sources:
                    continue
                seen_sources.add(src)
                pred = m.get('prediction', 'home')
                conf = min(75, max(30, 50 + (5 if pred == 'home' else 0)))
                results.append({
                    'platform': src,
                    'prediction': pred,
                    'confidence': conf,
                    'style': '外部预测源',
                    'reasons': ['外部数据源预测'],
                    'data_source': 'external',
                })
            return results
        except:
            return []

    def _count_platform_votes(self, platforms, model_probs):
        """统计各平台的投票分布"""
        votes = {'home': 0, 'draw': 0, 'away': 0, 'total': len(platforms)}
        conf_sum = {'home': 0, 'draw': 0, 'away': 0}
        for pl in platforms:
            pred = pl.get('prediction', '')
            if pred in votes:
                votes[pred] += 1
                conf_sum[pred] += pl.get('confidence', 0)
        # 加权投票（置信度加权）
        weighted = {}
        for key in ['home', 'draw', 'away']:
            weighted[key] = round(conf_sum[key] / votes[key], 1) if votes[key] > 0 else 0
        # 模型本身也算一票（权重最高）
        model_best = max(model_probs, key=model_probs.get)
        votes[model_best] += 1
        votes['total'] += 1
        return {
            'votes': votes,
            'weighted_confidence': weighted,
            'model_vote': model_best,
            'consensus': 'strong' if votes[max(votes, key=lambda k: votes[k] if k != 'total' else -1)] >= votes['total'] * 0.6 else 'moderate' if votes[max(votes, key=lambda k: votes[k] if k != 'total' else -1)] >= votes['total'] * 0.4 else 'weak',
        }

    def _build_summary(self, home, away, hs, aws, diff, probs, h2h, odds, hf, af, news=None, ext=None, is_close=False, prob_gap=0, final_pred=None, final_conf=None):
        s = []
        # 实力对比 — 有赔率时用赔率推断，没有时用评分
        odds_live = odds.get('live', {}) if isinstance(odds, dict) else {}
        if odds_live and odds_live.get('home', 0) > 0:
            h_odds = odds_live['home']; a_odds = odds_live['away']
            if h_odds < 1.4:
                s.append(home + '是绝对热门（赔率' + str(round(h_odds,2)) + '）')
            elif a_odds < 1.4:
                s.append(away + '是绝对热门（赔率' + str(round(a_odds,2)) + '）')
            elif h_odds < 1.8:
                s.append(home + '被市场看好（赔率' + str(round(h_odds,2)) + '）')
            elif a_odds < 1.8:
                s.append(away + '被市场看好（赔率' + str(round(a_odds,2)) + '）')
            elif h_odds < a_odds:
                s.append(home + '稍占优势（赔率' + str(round(h_odds,2)) + '/' + str(round(a_odds,2)) + '）')
            elif a_odds < h_odds:
                s.append(away + '稍占优势（赔率' + str(round(a_odds,2)) + '/' + str(round(h_odds,2)) + '）')
            else:
                d_odds = odds_live.get('draw', 3)
                s.append('赔率接近（' + str(round(h_odds,2)) + '/' + str(round(d_odds,2)) + '/' + str(round(a_odds,2)) + '）')
        elif abs(diff) > 15:
            stronger = home if diff > 0 else away
            s.append(stronger + '实力碾压')
        elif abs(diff) > 8:
            stronger = home if diff > 0 else away
            s.append(stronger + '实力占优')
        elif abs(diff) > 3:
            stronger = home if diff > 0 else away
            s.append(stronger + '稍占上风')
        else:
            s.append('实力接近')
        if final_pred and final_conf:
            names = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
            s.append('AI预测' + names.get(final_pred, final_pred) + '，置信度' + str(final_conf) + '%')
        else:
            best = max(probs, key=probs.get)
            names = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
            s.append('AI预测' + names[best] + '，概率' + str(probs[best]) + '%')
        # 接近比赛警告（只在真正胶着时）
        if is_close and prob_gap < 10:
            s.append('⚠ 概率接近，建议谨慎')
        # 赔率分析（有真实赔率时替代合成交锋/状态数据）
        if odds_live and odds_live.get('home', 0) > 0:
            h_odds = odds_live['home']; d_odds = odds_live.get('draw', 0); a_odds = odds_live['away']
            # 赔率变化信号（如果有）
            odds_signal = odds.get('odds_change_signal') if isinstance(odds, dict) else None
            if odds_signal:
                s.append('市场信号: ' + str(odds_signal))
            # 隐含概率
            total_inv = 1/h_odds + 1/d_odds + 1/a_odds
            imp_h = round(1/h_odds / total_inv * 100, 1)
            imp_d = round(1/d_odds / total_inv * 100, 1)
            imp_a = round(1/a_odds / total_inv * 100, 1)
            s.append(f'市场隐含概率: 主{imp_h}% 平{imp_d}% 客{imp_a}%')
        else:
            # 无赔率时用历史数据
            if h2h.get('total', 0) > 0:
                hw = str(h2h['home_wins']); dr = str(h2h['draws']); aw = str(h2h['away_wins'])
                s.append('交锋: 主' + hw + '胜' + dr + '平' + aw + '负')
            hp = hf.get('pts', 0); ap = af.get('pts', 0)
            if hp > ap + 3: s.append('主队近期状态更好')
            elif ap > hp + 3: s.append('客队近期状态更好')
        odds_live = odds.get('live', {}) if isinstance(odds, dict) else {}
        if odds_live and odds_live.get('home', 0) > 0:
            ho = str(round(odds_live['home'], 2))
            do = str(round(odds_live['draw'], 2))
            ao = str(round(odds_live['away'], 2))
            s.append('即时赔率: ' + ho + '/' + do + '/' + ao)
        if odds.get('odds_change_signal'):
            s.append('[赔率信号] ' + str(odds['odds_change_signal']))
        if news:
            for inj in news.get('home_injuries', []):
                s.append('[伤病] ' + home + ': ' + inj)
            for inj in news.get('away_injuries', []):
                s.append('[伤病] ' + away + ': ' + inj)
            w = news.get('weather', '晴')
            if w not in ['晴', '多云']:
                s.append('[天气] ' + w + '，场地湿滑影响发挥')
        if ext and ext.get('available'):
            s.append('[参考] 已获取Forebet国际预测数据')
        return s
