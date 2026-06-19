"""
更新赔率任务 — 体彩官方 + 国际博彩公司赔率
"""
from datetime import datetime
import logging
import json
import urllib.request
import ssl
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)

# 体彩官方赔率API
SPORTTERY_API = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'


def update_odds_task():
    """更新赔率：体彩官网 + The Odds API 国际赔率"""
    logger.info("开始更新赔率数据...")
    updated = 0

    try:
        with db_cursor() as cur:
            # ── 1. 体彩官方赔率 ──
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(SPORTTERY_API,
                headers={'User-Agent': 'Mozilla/5.0',
                         'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/'})
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            for info in data.get('value', {}).get('matchInfoList', []):
                for m in info.get('subMatchList', []):
                    mn = m.get('matchNumStr', '')
                    md = m.get('matchDate', '')
                    mid = f'JCZQ_{mn}_{md}' if md else f'JCZQ_{mn}'

                    for pool in m.get('oddsList', []):
                        if pool.get('poolCode') == 'HAD':
                            ho, do, ao = pool.get('h', ''), pool.get('d', ''), pool.get('a', '')
                            if ho and do and ao:
                                cur.execute('''SELECT home_odds, draw_odds, away_odds FROM odds
                                    WHERE match_id=%s AND bookmaker=%s ORDER BY created_at DESC LIMIT 1''',
                                    (mid, 'sporttery_cn'))
                                old = cur.fetchone()
                                changed = not old or (
                                    abs(float(ho) - float(old[0])) >= 0.01 or
                                    abs(float(do) - float(old[1])) >= 0.01 or
                                    abs(float(ao) - float(old[2])) >= 0.01
                                )
                                if changed:
                                    cur.execute('''INSERT INTO odds
                                        (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening, collect_time)
                                        VALUES (%s,%s,%s,%s,%s,0,%s)''',
                                        (mid, 'sporttery_cn', ho, do, ao, datetime.now()))
                                    updated += 1
                            break

            # ── 2. 国际赔率 (The Odds API) ──
            try:
                _fetch_international_odds(cur)
            except Exception as e:
                logger.warning(f"国际赔率获取失败: {e}")

        logger.info(f"赔率更新完成: 体彩变化{updated}条")

    except Exception as e:
        logger.error(f"赔率更新失败: {e}")


def _fetch_international_odds(cur):
    """从 The Odds API 获取国际博彩公司赔率"""
    ODDS_API_KEY = '63e6c2103ea9f9a8fe8509f2add255b0'
    # 世界杯对应的 sport key
    url = f'https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/?apiKey={ODDS_API_KEY}&regions=uk,eu&markets=h2h&oddsFormat=decimal'

    req = urllib.request.Request(url,
        headers={'User-Agent': 'FootballPredict/1.0', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return

    bm_map = {
        'Bet365': 'bet365', 'William Hill': 'william_hill',
        'Ladbrokes': 'ladbrokes', 'Pinnacle': 'pinnacle',
        'Betfair': 'betfair', 'Unibet': 'unibet',
        'Marathonbet': 'marathon', '1XBet': '1xbet',
    }

    for match in data:
        home_team = match.get('home_team', '')
        away_team = match.get('away_team', '')
        # 查找 DB 中匹配的比赛
        cur.execute('''SELECT match_id FROM matches WHERE home_team_name=%s AND away_team_name=%s''',
                    (home_team, away_team))
        db_match = cur.fetchone()
        if not db_match:
            continue
        match_id = db_match[0]

        for bm in match.get('bookmakers', [])[:8]:
            name = bm.get('title', '')
            db_name = bm_map.get(name, name.lower().replace(' ', '_'))
            for market in bm.get('markets', []):
                if market.get('key') != 'h2h':
                    continue
                outcomes = market.get('outcomes', [])
                ho = do = ao = None
                for o in outcomes:
                    if o['name'] == home_team: ho = o['price']
                    elif o['name'] == away_team: ao = o['price']
                    elif o['name'] == 'Draw': do = o['price']
                if ho and do and ao:
                    cur.execute('''INSERT INTO odds
                        (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening, collect_time)
                        VALUES (%s,%s,%s,%s,%s,0,%s)
                        ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds),
                        draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)''',
                        (match_id, db_name, ho, do, ao, datetime.now()))
                break
