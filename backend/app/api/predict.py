"""
综合预测API - 整合多平台数据和神经网络预测
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import re
import logging

from app.db_helper import db_cursor

router = APIRouter()
logger = logging.getLogger(__name__)

# 比分验证：检查比分是否与预测结果类型一致
def _score_matches_prediction(score: str, prediction: str) -> bool:
    """验证比分是否与预测结果一致。预测主胜时比分必须是主队赢，预测客胜时客队必须赢。"""
    if not score or '-' not in score:
        return False
    parts = score.split('-')
    if len(parts) != 2:
        return False
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if prediction == 'home':
        return h > a
    elif prediction == 'away':
        return a > h
    elif prediction == 'draw':
        return h == a
    return True

def _generate_default_score(prediction: str) -> str:
    """根据预测结果生成默认比分"""
    if prediction == 'home':
        return '2-0'
    elif prediction == 'draw':
        return '1-1'
    elif prediction == 'away':
        return '0-2'
    return '1-0'


class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    league: Optional[str] = ""


@router.post("/generate")
async def generate_prediction(request: PredictRequest):
    """生成综合预测"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    # 使用全局缓存的预测器
    try:
        from app.main import _get_predictor
        service = _get_predictor()
    except Exception:
        from services.prediction_service import PredictionService
        service = PredictionService()
    result = service.generate_prediction(
        home_team=request.home_team, away_team=request.away_team, league=request.league)
    return result


@router.get("/match/{match_id}")
async def get_match_prediction(match_id: str):
    """获取某场比赛的综合预测"""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT league_name, home_team_name, away_team_name FROM matches WHERE match_id = %s", (match_id,))
            row = cur.fetchone()
        if not row:
            return {"error": "比赛不存在"}
        league, home_team, away_team = row
        from app.main import _get_predictor
        service = _get_predictor()
        result = service.generate_prediction(home_team, away_team, league)
        result['match_id'] = match_id
        return result
    except Exception as e:
        return {"error": str(e)}


@router.post("/batch")
async def batch_predict():
    """批量预测 — 赔率没变用缓存，变了才重跑AI引擎"""
    from app.models.prediction import PredictionHistory
    from app.database import SessionLocal
    from datetime import datetime, timedelta
    import json as _json

    try:
        from app.main import _get_predictor
        predictor = _get_predictor()
    except Exception:
        from services.prediction_service import PredictionService
        predictor = PredictionService()

    today = datetime.now().strftime('%Y-%m-%d')
    three_hours_ago = (datetime.now() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
    rows = []

    three_days_later = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    try:
        with db_cursor() as cur:
            cur.execute("""SELECT match_id, league_name, home_team_name, away_team_name, match_time
                FROM matches WHERE match_time >= %s AND match_time < %s AND match_time > %s ORDER BY match_time""",
                (today, three_days_later + ' 23:59:59', three_hours_ago))
            rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"Failed to fetch matches from DB: {e}")

    if not rows:
        try:
            import urllib.request
            API_URL = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'
            hdrs = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/'}
            req = urllib.request.Request(API_URL, headers=hdrs)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
            match_list = data.get('value', {}).get('matchInfoList', [])
            with db_cursor() as cur:
                for info in match_list:
                    for m in info.get('subMatchList', []):
                        h = m.get('homeTeamAllName', '')
                        a = m.get('awayTeamAllName', '')
                        mn = m.get('matchNumStr', '')
                        md = m.get('matchDate', '')
                        mt = m.get('matchTime', '00:00:00')
                        lg = m.get('leagueAllName', m.get('leagueName', '国际赛'))
                        if not h or not a or not mn:
                            continue
                        mid = f'JCZQ_{mn}_{md}' if md else f'JCZQ_{mn}'
                        ft = f'{md} {mt}' if md else ''
                        rows.append((mid, lg, h, a, ft))
                        cur.execute('''DELETE FROM matches WHERE home_team_name=%s AND away_team_name=%s
                            AND match_time=%s AND match_id != %s''', (h, a, ft, mid))
                        cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time)
                            VALUES (%s,%s,%s,%s,%s)
                            ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), match_time=VALUES(match_time)''',
                            (mid, lg, h, a, ft))
                        for pool in m.get('oddsList', []):
                            if pool.get('poolCode') == 'HAD':
                                ho2, do2, ao2 = pool.get('h', ''), pool.get('d', ''), pool.get('a', '')
                                if ho2 and do2 and ao2:
                                    cur.execute('''INSERT INTO odds (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening)
                                        VALUES (%s,%s,%s,%s,%s,0)
                                        ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds), draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)''',
                                        (mid, 'sporttery_cn', ho2, do2, ao2))
                                break
        except Exception as e:
            logger.warning(f"Sporttery API fetch failed: {e}")

    results = []
    db = SessionLocal()
    try:
        for row in rows:
            mid, league, home, away, mtime = row
            try:
                existing = db.query(PredictionHistory).filter(PredictionHistory.match_id == mid).order_by(PredictionHistory.id.desc()).first()
                use_cache = False

                if existing and existing.detail_json:
                    use_cache = True
                    try:
                        with db_cursor() as cur:
                            cur.execute('SELECT home_odds, draw_odds, away_odds FROM odds WHERE match_id=%s AND bookmaker=%s ORDER BY created_at DESC LIMIT 2', (mid, 'sporttery_cn'))
                            orows = cur.fetchall()
                        if len(orows) >= 2:
                            n, o = orows[0], orows[1]
                            if abs(float(n[0]) - float(o[0])) >= 0.01 or abs(float(n[1]) - float(o[1])) >= 0.01 or abs(float(n[2]) - float(o[2])) >= 0.01:
                                use_cache = False
                    except Exception:
                        use_cache = True

                if use_cache:
                    cached = _json.loads(existing.detail_json)
                    cached_at = str(existing.created_at)[:16] if existing.created_at else ''
                    cached_pred = existing.prediction_result or 'home'
                    cached_pname = existing.prediction_name or '主胜'
                    cached_conf = float(existing.confidence or 50)
                    for line in cached.get('analysis_summary', []):
                        if 'AI预测' in line:
                            if '主胜' in line:
                                cached_pred, cached_pname = 'home', '主胜'
                            elif '平局' in line:
                                cached_pred, cached_pname = 'draw', '平局'
                            elif '客胜' in line:
                                cached_pred, cached_pname = 'away', '客胜'
                            m = re.search(r'置信度(\d+\.?\d*)%', line)
                            if m:
                                cached_conf = float(m.group(1))
                            break
                    cached_score = existing.predicted_score or ''
                    if cached_score and not _score_matches_prediction(cached_score, cached_pred):
                        cached_score = _generate_default_score(cached_pred)
                    results.append({
                        'match_id': mid, 'league_name': league,
                        'home_team_name': home, 'away_team_name': away,
                        'match_time': str(mtime),
                        'prediction': cached_pred,
                        'prediction_name': cached_pname,
                        'confidence': cached_conf,
                        'probabilities': cached.get('probabilities', {}),
                        'predicted_score': cached_score,
                        'platform_predictions': cached.get('platform_predictions', []),
                        'platform_votes': cached.get('platform_votes', {}),
                        'odds_analysis': cached.get('odds_analysis', {}),
                        'team_analysis': cached.get('team_analysis', {}),
                        'h2h_analysis': cached.get('h2h_analysis', {}),
                        'news_analysis': cached.get('news_analysis', {}),
                        'analysis_summary': cached.get('analysis_summary', []),
                        'from_cache': True,
                        'predicted_at': cached_at,
                    })
                else:
                    pred = predictor.generate_prediction(home, away, league, match_id=mid)
                    p = pred['prediction']
                    score = p.get('predicted_score', '')
                    if score and not _score_matches_prediction(score, p['prediction']):
                        score = _generate_default_score(p['prediction'])
                    result = {
                        'match_id': mid, 'league_name': league,
                        'home_team_name': home, 'away_team_name': away,
                        'match_time': str(mtime),
                        'prediction': p['prediction'],
                        'prediction_name': p['prediction_name'],
                        'confidence': p['confidence'],
                        'probabilities': p['probabilities'],
                        'predicted_score': score,
                        'is_close_match': p.get('is_close_match', False),
                        'prob_gap': p.get('prob_gap', 0),
                        'platform_predictions': pred.get('platform_predictions', []),
                        'platform_votes': pred.get('platform_votes', {}),
                        'odds_analysis': pred.get('odds_analysis', {}),
                        'team_analysis': pred.get('team_analysis', {}),
                        'h2h_analysis': pred.get('h2h_analysis', {}),
                        'news_analysis': pred.get('news_analysis', {}),
                        'analysis_summary': pred.get('analysis_summary', []),
                        'from_cache': False,
                        'predicted_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    }
                    results.append(result)

                    dc = _json.dumps({
                        'probabilities': p.get('probabilities', {}),
                        'odds_analysis': pred.get('odds_analysis', {}),
                        'team_analysis': pred.get('team_analysis', {}),
                        'h2h_analysis': pred.get('h2h_analysis', {}),
                        'platform_predictions': pred.get('platform_predictions', []),
                        'platform_votes': pred.get('platform_votes', {}),
                        'analysis_summary': pred.get('analysis_summary', []),
                        'news_analysis': pred.get('news_analysis', {}),
                    }, ensure_ascii=False)
                    try:
                        with db_cursor() as cur:
                            cur.execute("""INSERT INTO prediction_history
                                (match_id, match_date, league, home_team, away_team,
                                 prediction_result, prediction_name, confidence, predicted_score, detail_json, is_correct)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                                ON DUPLICATE KEY UPDATE
                                 prediction_result=VALUES(prediction_result),
                                 prediction_name=VALUES(prediction_name),
                                 confidence=VALUES(confidence),
                                 predicted_score=VALUES(predicted_score),
                                 detail_json=VALUES(detail_json),
                                 match_date=VALUES(match_date)""",
                                (mid, datetime.now(), league, home, away,
                                 p['prediction'], p['prediction_name'], p['confidence'],
                                 score, dc))
                    except Exception as e:
                        logger.warning(f"Save prediction failed for {mid}: {e}")
            except Exception as e:
                results.append({
                    'match_id': mid, 'league_name': league,
                    'home_team_name': home, 'away_team_name': away,
                    'match_time': str(mtime), 'error': str(e),
                })
        db.commit()
    finally:
        db.close()

    return {"total": len(results), "results": results}
