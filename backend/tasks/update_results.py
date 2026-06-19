"""
比赛结果回写 — 比赛结束后1小时从体彩API拉比分更新
"""
import logging
import requests
from datetime import datetime, timedelta
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)

RESULT_API = 'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
    'Referer': 'https://m.sporttery.cn/',
}


def _fix_wrong_is_correct():
    """修复 is_correct 与 actual_result 不一致的记录"""
    try:
        with db_cursor() as cur:
            # 修复：prediction_result == actual_result 但 is_correct != 1
            cur.execute('''
                UPDATE prediction_history
                SET is_correct = 1
                WHERE prediction_result = actual_result
                  AND actual_result IS NOT NULL
                  AND actual_result != ''
                  AND is_correct != 1
            ''')
            fixed_correct = cur.rowcount

            # 修复：prediction_result != actual_result 但 is_correct != 2
            cur.execute('''
                UPDATE prediction_history
                SET is_correct = 2
                WHERE prediction_result != actual_result
                  AND actual_result IS NOT NULL
                  AND actual_result != ''
                  AND prediction_result IS NOT NULL
                  AND is_correct != 2
            ''')
            fixed_wrong = cur.rowcount

            if fixed_correct > 0 or fixed_wrong > 0:
                logger.info(f"修正 is_correct: {fixed_correct} 条改为正确, {fixed_wrong} 条改为错误")
    except Exception as e:
        logger.debug(f"is_correct 修正跳过: {e}")


def update_results_task():
    """比赛结束1小时后，拉比分回写 prediction_history"""
    # 先修复可能错误的 is_correct 记录
    _fix_wrong_is_correct()

    with db_cursor() as cur:
        one_hour_ago = datetime.now() - timedelta(hours=1)
        three_days_ago = datetime.now() - timedelta(days=3)

        cur.execute('''SELECT id, match_id, match_date, prediction_result
            FROM prediction_history
            WHERE (is_correct = 0 OR actual_result IS NULL OR actual_result = '')
              AND match_date > %s
              AND match_date < %s
            ORDER BY match_date DESC''',
            (three_days_ago, one_hour_ago))
        pending = cur.fetchall()

        if not pending:
            logger.info("没有比赛结束满1小时待更新的记录")
            return

        logger.info(f"待更新: {len(pending)} 场")

        # 从 match_id 中提取实际比赛日期（格式: JCZQ_周X001_2026-06-15）
        dates = sorted(set(
            mid.split('_')[-1] for _, mid, _, _ in pending if mid and '_' in mid
        ))

        results = {}
        for date_str in dates:
            try:
                resp = requests.get(RESULT_API, params={
                    'matchPage': 1,
                    'matchBeginDate': date_str,
                    'matchEndDate': date_str,
                }, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    continue
                for m in resp.json().get('value', {}).get('matchResult', []):
                    if m.get('matchResultStatus') != '2':
                        continue
                    mn = m.get('matchNumStr', '')
                    md = m.get('matchDate', '')
                    score_raw = m.get('sectionsNo999', '')
                    if not mn or not md or not score_raw:
                        continue
                    parts = score_raw.split(',')
                    score = parts[-1].strip().replace(':', '-')
                    if '-' not in score:
                        continue
                    try:
                        h, a = score.split('-')
                        h, a = int(h), int(a)
                    except ValueError:
                        continue
                    results[f'JCZQ_{mn}_{md}'] = {
                        'home_score': h, 'away_score': a, 'score': score,
                    }
            except Exception as e:
                logger.warning(f"拉取 {date_str} 比分失败: {e}")

        updated = 0
        for pid, mid, _, pred_result in pending:
            r = results.get(mid)
            if not r:
                continue

            actual = ('home' if r['home_score'] > r['away_score'] else
                      'away' if r['away_score'] > r['home_score'] else 'draw')
            is_correct = 1 if actual == pred_result else 2

            cur.execute('''UPDATE prediction_history
                SET actual_result=%s, actual_score=%s, home_score=%s, away_score=%s, is_correct=%s
                WHERE id=%s''',
                (actual, r['score'], r['home_score'], r['away_score'], is_correct, pid))
            updated += 1

    logger.info(f"结果更新完成: {updated}/{len(pending)} 条")
