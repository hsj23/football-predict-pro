"""
实时比分API — 轮询体彩官方接口
"""
from fastapi import APIRouter
import requests, time
from datetime import datetime, timedelta

router = APIRouter()

RESULT_API = 'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.sporttery.cn/'}

_cache = {'data': [], 'time': 0}


@router.get("/scores")
async def live_scores():
    now = time.time()
    if _cache['data'] and now - _cache['time'] < 5:
        return _cache['data']

    results = []
    for d in (-1, 0, 1, 2):
        date = (datetime.now() + timedelta(days=d)).strftime('%Y-%m-%d')
        try:
            resp = requests.get(RESULT_API, params={
                'matchPage': 1, 'matchBeginDate': date, 'matchEndDate': date
            }, headers=HEADERS, timeout=8)
            for m in resp.json().get('value', {}).get('matchResult', []):
                mn = m.get('matchNumStr', '')
                home = m.get('allHomeTeam', '')
                away = m.get('allAwayTeam', '')
                if not home or not away or not mn:
                    continue

                sc = m.get('matchResultStatus', '0')
                status = {'0': 'scheduled', '1': 'live', '2': 'finished'}.get(sc, 'scheduled')

                score_raw = m.get('sectionsNo999', '')
                half, full = '', ''
                if score_raw:
                    p = score_raw.split(',')
                    half = p[0].strip() if p else ''
                    full = p[-1].strip() if p else ''

                results.append({
                    'match_id': f'JCZQ_{mn}_{m.get("matchDate", date)}',
                    'match_num': mn,
                    'home_team': home,
                    'away_team': away,
                    'league': m.get('leagueName', ''),
                    'match_date': m.get('matchDate', date),
                    'status': status,
                    'status_code': sc,
                    'half_score': half,
                    'full_score': full,
                    'odds': {'h': m.get('h', ''), 'd': m.get('d', ''), 'a': m.get('a', '')},
                })
        except:
            pass

    _cache['data'] = results
    _cache['time'] = now
    return results
