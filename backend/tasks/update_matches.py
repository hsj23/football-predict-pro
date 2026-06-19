"""
更新比赛任务 — 仅使用体彩官方API
"""
from datetime import datetime, timedelta
import logging
import json
import urllib.request
import ssl
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)

SPORTTERY_API = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'
API_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/',
}


def update_matches_task():
    """从体彩官方API更新比赛列表"""
    logger.info("开始从体彩API更新比赛列表...")

    try:
        # 获取体彩比赛数据
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(SPORTTERY_API, headers=API_HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        match_list = data.get('value', {}).get('matchInfoList', [])

        with db_cursor() as cur:
            inserted = 0
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

                    cur.execute('''DELETE FROM matches WHERE home_team_name=%s
                        AND away_team_name=%s AND match_time=%s AND match_id != %s''',
                        (h, a, ft, mid))

                    cur.execute('''INSERT INTO matches
                        (match_id, league_name, home_team_name, away_team_name, match_time, status)
                        VALUES (%s,%s,%s,%s,%s,'scheduled')
                        ON DUPLICATE KEY UPDATE league_name=VALUES(league_name),
                        match_time=VALUES(match_time)''',
                        (mid, lg, h, a, ft))

                    for pool in m.get('oddsList', []):
                        if pool.get('poolCode') == 'HAD':
                            ho, do, ao = pool.get('h', ''), pool.get('d', ''), pool.get('a', '')
                            if ho and do and ao:
                                cur.execute('''INSERT INTO odds
                                    (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening)
                                    VALUES (%s,%s,%s,%s,%s,0)
                                    ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds),
                                    draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)''',
                                    (mid, 'sporttery_cn', ho, do, ao))
                            break

                    inserted += 1

        logger.info(f"体彩比赛更新完成: {inserted} 场")

    except Exception as e:
        logger.error(f"体彩比赛更新失败: {e}")


def save_match(db, match_data):
    """保留接口兼容，不再使用"""
    pass


def parse_match_time(time_str):
    """保留接口兼容"""
    return None
