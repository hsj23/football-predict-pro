"""
ROI 评估与回测框架
用于评估预测系统的投注价值（Return on Investment）
"""
import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


def calculate_roi(predictions: List[dict], strategy: str = 'flat') -> dict:
    """
    计算预测系统的 ROI

    Args:
        predictions: 预测记录列表，每条需包含:
            - prediction: 'home'/'draw'/'away'
            - actual_result: 'home'/'draw'/'away'
            - confidence: 置信度 (0-100)
            - odds_home, odds_draw, odds_away: 赔率 (可选)
        strategy: 投注策略
            - 'flat': 固定金额投注每场
            - 'confidence': 按置信度调整投注金额
            - 'value': 仅投注有期望价值的场次

    Returns:
        dict: ROI 统计结果
    """
    if not predictions:
        return {'total': 0, 'roi': 0, 'profit': 0}

    total_bets = 0
    total_stake = 0.0
    total_profit = 0.0
    correct = 0
    results_by_type = defaultdict(lambda: {'total': 0, 'correct': 0, 'stake': 0, 'profit': 0})
    results_by_confidence = defaultdict(lambda: {'total': 0, 'correct': 0, 'stake': 0, 'profit': 0})

    for p in predictions:
        pred = p.get('prediction')
        actual = p.get('actual_result')
        confidence = p.get('confidence', 50)

        if not pred or not actual:
            continue

        # 获取对应赔率
        odds_map = {
            'home': p.get('odds_home'),
            'draw': p.get('odds_draw'),
            'away': p.get('odds_away'),
        }
        odds = odds_map.get(pred)

        # 确定投注金额
        if strategy == 'flat':
            stake = 1.0
        elif strategy == 'confidence':
            stake = max(0.5, confidence / 50)  # 50%置信度=1单位，100%=2单位
        elif strategy == 'value':
            # 仅当有正期望价值时投注
            if not odds or confidence <= 0:
                continue
            implied_prob = 1.0 / odds
            model_prob = confidence / 100.0
            if model_prob <= implied_prob:
                continue  # 无价值，跳过
            stake = 1.0
        else:
            stake = 1.0

        total_bets += 1
        total_stake += stake

        is_correct = (pred == actual)
        if is_correct:
            correct += 1
            if odds:
                profit = stake * (odds - 1)
            else:
                profit = stake * 0.8  # 无赔率时假设平均赔率1.8
        else:
            profit = -stake

        total_profit += profit

        # 按预测类型统计
        results_by_type[pred]['total'] += 1
        results_by_type[pred]['stake'] += stake
        results_by_type[pred]['profit'] += profit
        if is_correct:
            results_by_type[pred]['correct'] += 1

        # 按置信度区间统计
        conf_bucket = int(confidence / 10) * 10
        results_by_confidence[conf_bucket]['total'] += 1
        results_by_confidence[conf_bucket]['stake'] += stake
        results_by_confidence[conf_bucket]['profit'] += profit
        if is_correct:
            results_by_confidence[conf_bucket]['correct'] += 1

    roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
    accuracy = (correct / total_bets * 100) if total_bets > 0 else 0

    return {
        'total_bets': total_bets,
        'correct': correct,
        'accuracy': round(accuracy, 2),
        'total_stake': round(total_stake, 2),
        'total_profit': round(total_profit, 2),
        'roi': round(roi, 2),
        'by_type': {
            t: {
                'total': d['total'],
                'correct': d['correct'],
                'accuracy': round(d['correct'] / d['total'] * 100, 1) if d['total'] > 0 else 0,
                'roi': round(d['profit'] / d['stake'] * 100, 1) if d['stake'] > 0 else 0,
                'profit': round(d['profit'], 2),
            }
            for t, d in results_by_type.items()
        },
        'by_confidence': {
            bucket: {
                'total': d['total'],
                'correct': d['correct'],
                'accuracy': round(d['correct'] / d['total'] * 100, 1) if d['total'] > 0 else 0,
                'roi': round(d['profit'] / d['stake'] * 100, 1) if d['stake'] > 0 else 0,
            }
            for bucket, d in sorted(results_by_confidence.items())
        },
    }


def backtest_from_db() -> Optional[dict]:
    """
    从数据库读取历史预测进行回测

    Returns:
        dict: 回测结果，包含 ROI 和各类统计
    """
    try:
        from app.db_helper import db_cursor
        with db_cursor() as cur:
            # 查询有实际结果的预测记录
            cur.execute('''
                SELECT ph.prediction_result, ph.actual_result, ph.confidence,
                       ph.match_id, ph.detail_json
                FROM prediction_history ph
                WHERE ph.is_correct IN (1, 2)
                  AND ph.actual_result IS NOT NULL
                  AND ph.prediction_result IS NOT NULL
                ORDER BY ph.match_date DESC
            ''')
            rows = cur.fetchall()

        if not rows:
            logger.info("No historical predictions with results found")
            return None

        predictions = []
        for pred_result, actual_result, confidence, match_id, detail_json in rows:
            # 从 detail_json 提取赔率
            odds_home = odds_draw = odds_away = None
            if detail_json:
                try:
                    import json
                    detail = json.loads(detail_json)
                    odds_analysis = detail.get('odds_analysis', {})
                    if odds_analysis and 'avg_odds' in odds_analysis:
                        avg = odds_analysis['avg_odds']
                        odds_home = avg.get('home')
                        odds_draw = avg.get('draw')
                        odds_away = avg.get('away')
                except Exception:
                    pass

            predictions.append({
                'prediction': pred_result,
                'actual_result': actual_result,
                'confidence': float(confidence) if confidence else 50,
                'odds_home': odds_home,
                'odds_draw': odds_draw,
                'odds_away': odds_away,
            })

        # 计算策略的 ROI
        results = {
            'total_records': len(predictions),
            'flat': calculate_roi(predictions, 'flat'),
        }

        # 只在有赔率数据时计算 value 策略
        has_odds = any(p.get('odds_home') for p in predictions)
        if has_odds:
            results['value'] = calculate_roi(predictions, 'value')
        else:
            results['value'] = {'total_bets': 0, 'note': '无赔率数据，无法计算价值投注'}

        logger.info(f"Backtest: {results['total_records']} records, "
                    f"accuracy={results['flat']['accuracy']}%, "
                    f"flat ROI={results['flat']['roi']}%")

        return results

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return None


def evaluate_calibration(predictions: List[dict]) -> dict:
    """
    评估校准质量 — 模型说60%的事件是否真的发生了60%？

    Returns:
        dict: 校准曲线数据 (reliability diagram)
    """
    buckets = defaultdict(lambda: {'predicted': [], 'actual': []})

    for p in predictions:
        pred = p.get('prediction')
        actual = p.get('actual_result')
        probs = p.get('probabilities', {})

        if not pred or not actual or not probs:
            continue

        # 按预测概率分桶
        pred_prob = probs.get(pred, 50)
        bucket = int(pred_prob / 10) * 10
        buckets[bucket]['predicted'].append(pred_prob / 100)
        buckets[bucket]['actual'].append(1 if pred == actual else 0)

    calibration = {}
    for bucket, data in sorted(buckets.items()):
        n = len(data['actual'])
        if n < 5:
            continue
        avg_predicted = sum(data['predicted']) / n
        avg_actual = sum(data['actual']) / n
        calibration[bucket] = {
            'count': n,
            'avg_predicted': round(avg_predicted * 100, 1),
            'avg_actual': round(avg_actual * 100, 1),
            'gap': round((avg_predicted - avg_actual) * 100, 1),  # 正=过度自信
        }

    return calibration
