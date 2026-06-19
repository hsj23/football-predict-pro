"""
更新预测任务 — 使用AI引擎批量预测（仅体彩比赛）
"""
import logging

logger = logging.getLogger(__name__)


def update_predictions_task():
    """批量预测所有待比赛场次"""
    logger.info("开始AI批量预测...")
    try:
        from services.prediction_service import PredictionService
        from app.db_helper import db_cursor
        from datetime import datetime, timedelta

        predictor = PredictionService()

        today = datetime.now().strftime('%Y-%m-%d')
        three_days_later = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')

        with db_cursor() as cur:
            cur.execute('''SELECT match_id, league_name, home_team_name, away_team_name
                FROM matches WHERE match_time >= %s AND match_time < %s ORDER BY match_time''',
                (today, three_days_later + ' 23:59:59'))
            rows = cur.fetchall()

        for mid, league, home, away in rows:
            try:
                pred = predictor.generate_prediction(home, away, league, match_id=mid)
                p = pred['prediction']
                score = p.get('predicted_score', '') or ''
                if not score:
                    score = _default_score(p['prediction'])
                elif not _score_ok(score, p['prediction']):
                    score = _default_score(p['prediction'])

                with db_cursor() as cur2:
                    cur2.execute('''INSERT INTO prediction_history
                        (match_id, match_date, league, home_team, away_team,
                         prediction_result, prediction_name, confidence, predicted_score, is_correct)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                        ON DUPLICATE KEY UPDATE
                         prediction_result=VALUES(prediction_result),
                         prediction_name=VALUES(prediction_name),
                         confidence=VALUES(confidence),
                         predicted_score=VALUES(predicted_score)''',
                        (mid, datetime.now(), league, home, away,
                         p['prediction'], p['prediction_name'], p['confidence'], score))
            except Exception as e:
                logger.warning(f"预测失败 {home} vs {away}: {e}")

        logger.info(f"AI批量预测完成: {len(rows)} 场")

    except Exception as e:
        logger.error(f"批量预测失败: {e}")


def _score_ok(score, prediction):
    try:
        h, a = map(int, str(score).split('-'))
        if prediction == 'home': return h > a
        if prediction == 'away': return a > h
        if prediction == 'draw': return h == a
    except:
        pass
    return False


def _default_score(prediction):
    return {'home': '2-0', 'draw': '1-1', 'away': '0-2'}.get(prediction, '1-0')
