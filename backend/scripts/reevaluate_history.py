"""
历史数据全量重评估脚本
使用最新 HybridPredictor 引擎重新预测所有有结果的历史比赛，
将预测结果更新到 prediction_history 表，并输出准确率报告。

用法:
  cd D:\小黄的助手\足彩预测系统\backend
  python scripts\reevaluate_history.py

可指定 --limit N 仅评估最近 N 场
       --source training|jczq|all  数据来源过滤
       --dry-run  只评估不写库
"""

import sys
import os
import json
import logging
import warnings
warnings.filterwarnings('ignore')
import time
from datetime import datetime
from collections import defaultdict

# 确保 backend 目录在 sys.path 中
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(BACKEND_DIR), 'data')
RESULT_CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}


def load_all_historical_matches():
    """加载所有有赔率+有比分的比赛（去重）"""
    matches = []
    seen = set()

    sources = [
        ('jczq_results.json', 'jczq'),
        ('training_data.json', 'training'),
    ]

    for filename, source in sources:
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            logger.warning(f"文件不存在: {path}")
            continue

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        logger.info(f"加载 {filename}: {len(data)} 条记录")

        for m in data:
            home = (m.get('home') or '').strip()
            away = (m.get('away') or '').strip()
            odds = m.get('odds', [])
            full_score = m.get('full_score', '')

            if not home or not away:
                continue
            if not odds or len(odds) != 3:
                continue
            if not full_score or ':' not in full_score:
                continue

            # 解析比分
            try:
                parts = full_score.split(':')
                hs, ags = int(parts[0]), int(parts[1])
            except (ValueError, IndexError):
                continue

            if hs > ags:
                actual = 'home'
            elif hs < ags:
                actual = 'away'
            else:
                actual = 'draw'

            # 去重 key
            # 统一队伍名（处理括号、空格差异）
            clean_home = home.split('(')[0].split('（')[0].strip().upper()
            clean_away = away.split('(')[0].split('（')[0].strip().upper()
            date = m.get('date', '')

            dedup_key = f"{clean_home}|{clean_away}|{date}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # 标准化赔率
            try:
                odds_float = [float(o) for o in odds[:3]]
            except (ValueError, TypeError):
                continue

            matches.append({
                'home': home,
                'away': away,
                'league': m.get('league', ''),
                'date': date or '未知',
                'odds': odds_float,
                'home_score': hs,
                'away_score': ags,
                'full_score': full_score,
                'actual': actual,
                'source': source,
            })

    # 按日期排序（最近的在前）
    matches.sort(key=lambda x: x['date'], reverse=True)
    logger.info(f"去重后共 {len(matches)} 场有效历史比赛")
    return matches


def resolve_result(home_score, away_score):
    if home_score > away_score:
        return 'home', '主胜'
    elif home_score < away_score:
        return 'away', '客胜'
    else:
        return 'draw', '平局'


def save_to_db(match, pred, actual, dry_run=False):
    """将预测结果写入 prediction_history 表"""
    if dry_run:
        return

    try:
        from app.db_helper import db_cursor
        mid = f"HIST_{match['date'].replace('-', '')}_{match['home'][:6]}_{match['away'][:6]}"
        match_date = match['date'] if match['date'] != '未知' else '2000-01-01'

        pred_result = pred['prediction']
        detail_json = json.dumps({
            'probabilities': pred.get('probabilities', {}),
            'engine': pred.get('engine', ''),
            'model_type': pred.get('model_type', ''),
            'is_close_match': pred.get('is_close_match', False),
        }, ensure_ascii=False)

        is_correct = 1 if pred_result == actual else 2

        with db_cursor() as cur:
            cur.execute("""INSERT INTO prediction_history
                (match_id, match_date, league, home_team, away_team,
                 prediction_result, prediction_name, confidence, predicted_score,
                 actual_result, actual_score, home_score, away_score,
                 is_correct, detail_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                 prediction_result=VALUES(prediction_result),
                 prediction_name=VALUES(prediction_name),
                 confidence=VALUES(confidence),
                 predicted_score=VALUES(predicted_score),
                 actual_result=VALUES(actual_result),
                 actual_score=VALUES(actual_score),
                 home_score=VALUES(home_score),
                 away_score=VALUES(away_score),
                 is_correct=VALUES(is_correct),
                 detail_json=VALUES(detail_json)""",
                (mid, match_date, match['league'], match['home'], match['away'],
                 pred_result, pred['prediction_name'], pred['confidence'],
                 pred.get('predicted_score', ''),
                 actual, match['full_score'], match['home_score'], match['away_score'],
                 is_correct, detail_json))
    except Exception as e:
        logger.warning(f"保存失败 {match['home']} vs {match['away']}: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='历史数据重评估')
    parser.add_argument('--limit', type=int, default=0, help='仅评估最近 N 场（0=全部）')
    parser.add_argument('--source', choices=['training', 'jczq', 'all'], default='all')
    parser.add_argument('--dry-run', action='store_true', help='只评估不写库')
    args = parser.parse_args()

    # 加载历史数据
    all_matches = load_all_historical_matches()

    if args.source != 'all':
        all_matches = [m for m in all_matches if m['source'] == args.source]
        logger.info(f"过滤来源={args.source}，剩余 {len(all_matches)} 场")

    if args.limit > 0:
        all_matches = all_matches[:args.limit]
        logger.info(f"限制为最近 {len(all_matches)} 场")

    logger.info(f"开始评估 {len(all_matches)} 场历史比赛...")

    # 初始化预测器（只初始化一次）
    from ml.hybrid_predictor import HybridPredictor
    logger.info("初始化 HybridPredictor...")
    predictor = HybridPredictor()
    logger.info("初始化完成")

    # 统计
    stats = {'total': 0, 'correct': 0, 'correct_home': 0, 'correct_draw': 0, 'correct_away': 0}
    stats['total_home'] = 0
    stats['total_draw'] = 0
    stats['total_away'] = 0
    stats['close_correct'] = 0
    stats['close_total'] = 0
    stats['by_league'] = defaultdict(lambda: {'total': 0, 'correct': 0})
    stats['errors'] = []

    start_time = time.time()

    for i, match in enumerate(all_matches):
        try:
            pred = predictor.predict(
                match['home'], match['away'], match['league'],
                match['odds']
            )
            actual = match['actual']
            is_correct = pred['prediction'] == actual

            # 更新统计
            stats['total'] += 1
            if is_correct:
                stats['correct'] += 1

            if actual == 'home':
                stats['total_home'] += 1
                if is_correct:
                    stats['correct_home'] += 1
            elif actual == 'draw':
                stats['total_draw'] += 1
                if is_correct:
                    stats['correct_draw'] += 1
            else:
                stats['total_away'] += 1
                if is_correct:
                    stats['correct_away'] += 1

            if pred.get('is_close_match'):
                stats['close_total'] += 1
                if is_correct:
                    stats['close_correct'] += 1

            lg = match['league'] or '未知'
            stats['by_league'][lg]['total'] += 1
            if is_correct:
                stats['by_league'][lg]['correct'] += 1

            # 写入DB
            if not args.dry_run:
                save_to_db(match, pred, actual)

            # 进度
            if (i + 1) % 100 == 0 or (i + 1) == len(all_matches):
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(all_matches) - i - 1) / rate if rate > 0 else 0
                acc = stats['correct'] / stats['total'] * 100 if stats['total'] > 0 else 0
                logger.info(
                    f"进度: {i+1}/{len(all_matches)} "
                    f"(准确率: {stats['correct']}/{stats['total']} = {acc:.1f}%) "
                    f"速度: {rate:.1f}场/秒 ETA: {eta:.0f}秒")

        except Exception as e:
            stats['errors'].append({
                'match': f"{match['home']} vs {match['away']}",
                'error': str(e)
            })
            logger.error(f"预测失败 {match['home']} vs {match['away']}: {e}")
            continue

    # 输出报告
    elapsed = time.time() - start_time
    print()
    print("=" * 70)
    print("  历史数据重评估报告")
    print(f"  引擎: HybridPredictor (XGBoost + Ensemble + Dixon-Coles + Elo + Odds)")
    print(f"  评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  耗时: {elapsed:.1f} 秒")
    print("=" * 70)
    print()

    total = stats['total']
    acc = stats['correct'] / total * 100 if total > 0 else 0
    print(f"  [总体] 准确率: {acc:.1f}% ({stats['correct']}/{total})")

    if stats['total_home'] > 0:
        ha = stats['correct_home'] / stats['total_home'] * 100
        print(f"     |- 主胜预测: {ha:.1f}% ({stats['correct_home']}/{stats['total_home']})")
    if stats['total_draw'] > 0:
        da = stats['correct_draw'] / stats['total_draw'] * 100
        print(f"     |- 平局预测: {da:.1f}% ({stats['correct_draw']}/{stats['total_draw']})")
    if stats['total_away'] > 0:
        aa = stats['correct_away'] / stats['total_away'] * 100
        print(f"     |- 客胜预测: {aa:.1f}% ({stats['correct_away']}/{stats['total_away']})")

    if stats['close_total'] > 0:
        ca = stats['close_correct'] / stats['close_total'] * 100
        print(f"  [接近] 实力接近场次: {ca:.1f}% ({stats['close_correct']}/{stats['close_total']})")

    print()
    print("  [联赛] 按联赛统计:")
    for lg, s in sorted(stats['by_league'].items(), key=lambda x: x[1]['total'], reverse=True):
        if s['total'] >= 3:
            lg_acc = s['correct'] / s['total'] * 100
            print(f"     {lg}: {lg_acc:.1f}% ({s['correct']}/{s['total']})")

    if stats['errors']:
        print(f"\n  [警告] 错误 ({len(stats['errors'])} 场):")
        for e in stats['errors'][:10]:
            print(f"     - {e['match']}: {e['error']}")

    if not args.dry_run:
        print(f"\n  [完成] 已更新 prediction_history 表")

    print()
    return stats


if __name__ == '__main__':
    main()
