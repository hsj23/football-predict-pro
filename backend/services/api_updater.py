"""
API数据更新器 - 使用体彩官方API自动获取比赛数据和赛果
不依赖Selenium，纯HTTP请求，稳定可靠
"""
import requests
import json
import time
import logging
from datetime import datetime, timedelta
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.sporttery.cn/',
}

RESULT_API = 'https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry'


def fetch_results_page(page, begin_date, end_date):
    """获取一页赛果数据"""
    try:
        resp = requests.get(RESULT_API, params={
            'matchPage': page,
            'matchBeginDate': begin_date,
            'matchEndDate': end_date,
        }, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('value', {})
    except Exception as e:
        logger.warning(f'API page {page} failed: {e}')
    return {}


def update_match_results(days=3):
    """更新最近的比赛结果到数据库"""
    today = datetime.now()
    begin = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')

    logger.info(f'Fetching results {begin} ~ {end}...')

    first = fetch_results_page(1, begin, end)
    matches = first.get('matchResult', [])
    total_pages = first.get('pages', 1)

    # Fetch remaining pages
    for page in range(2, min(total_pages + 1, 10)):
        time.sleep(0.3)
        data = fetch_results_page(page, begin, end)
        matches.extend(data.get('matchResult', []))

    logger.info(f'Got {len(matches)} results from API')

    if not matches:
        return 0

    try:
        with db_cursor() as cur:
            updated = 0
            for m in matches:
            home = m.get('allHomeTeam', m.get('homeTeam', ''))
            away = m.get('allAwayTeam', m.get('awayTeam', ''))
            league = m.get('leagueName', '')
            match_date = m.get('matchDate', '')
            match_num = m.get('matchNumStr', '')
            match_time_str = match_date  # API only gives date, not time

            # Parse score
            score_raw = m.get('sectionsNo999', '')
            full_score = ''
            home_score = away_score = 0
            if score_raw:
                parts = score_raw.split(',')
                full_score = parts[-1].strip()
                if ':' in full_score:
                    try:
                        hs, aws = full_score.split(':')
                        home_score, away_score = int(hs), int(aws)
                    except:
                        pass

            # 官网标记为完赛(matchResultStatus=2)才更新赛果
            actual = None
            if m.get('matchResultStatus') == '2' and full_score and ':' in full_score:
                if home_score > away_score:
                    actual = 'home'
                elif home_score < away_score:
                    actual = 'away'
                else:
                    actual = 'draw'

            # Match ID — JCZQ_比赛编号_日期，避免跨周覆盖
            match_id = f"JCZQ_{match_num}_{match_date}"
            match_id_short = f"JCZQ_{match_num}"
            match_id_long = f"JCZQ_{match_num}_{m.get('matchId', '')}"

            # Check if match exists (兼容三种格式)
            cur.execute('SELECT id FROM matches WHERE match_id=%s OR match_id=%s OR match_id=%s', (match_id, match_id_short, match_id_long))
            existing = cur.fetchone()

            if not existing:
                # Estimate match time based on match number
                try:
                    num = int(''.join(c for c in match_num if c.isdigit()))
                    hour = 13 + (num % 10)
                except:
                    hour = 20
                match_time = f'{match_date} {hour:02d}:00:00'

                cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time, status)
                    VALUES (%s,%s,%s,%s,%s,%s)''',
                    (match_id, league, home, away, match_time,
                     'finished' if actual else 'scheduled'))
                updated += 1

            # Update prediction_history with actual result
            if actual:
                cur.execute('SELECT id FROM prediction_history WHERE match_id=%s OR match_id=%s OR match_id=%s', (match_id, match_id_short, match_id_long))
                ph = cur.fetchone()
                if ph:
                    # Update whichever record exists
                    existing_id = ph[0]
                    cur.execute('''UPDATE prediction_history SET
                        actual_result=%s, actual_score=%s, home_score=%s, away_score=%s,
                        is_correct = CASE WHEN prediction_result=%s THEN 1 ELSE 2 END
                        WHERE id=%s''',
                        (actual, full_score, home_score, away_score, actual, existing_id))
                else:
                    # Create prediction history entry
                    cur.execute('''INSERT INTO prediction_history
                        (match_id, match_date, league, home_team, away_team,
                         actual_result, actual_score, home_score, away_score, is_correct)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,0)''',
                        (match_id, match_date, league, home, away,
                         actual, full_score, home_score, away_score))

            logger.info(f'Updated {updated} matches in DB')
        return updated

    except Exception as e:
        logger.error(f'DB update failed: {e}')
        return 0


def fetch_upcoming_matches():
    """从体彩官方API获取即将开赛的比赛列表（未来比赛）— 多源备选"""
    # 方法1: 体彩官方 Match Calculator API
    count = _fetch_sporttery_upcoming()
    if count > 0:
        logger.info(f'[Method 1] sporttery.cn: {count} matches')
        return count

    # 方法2: 体彩官网HTML页面解析
    logger.info('[Method 1] failed, trying [Method 2] sporttery HTML parse...')
    count = _fetch_upcoming_from_html()
    if count > 0:
        logger.info(f'[Method 2] sporttery HTML: {count} matches')
        return count

    # 方法3: 500彩票网
    logger.info('[Method 2] failed, trying [Method 3] 500.com...')
    count = _fetch_500_upcoming()
    if count > 0:
        logger.info(f'[Method 3] 500.com: {count} matches')
        return count

    logger.warning('All methods failed to fetch upcoming matches')
    return 0


def _fetch_sporttery_upcoming():
    """方法1: 体彩官方 getMatchCalculatorV1 API"""
    API_URL = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry'
    try:
        resp = requests.get(API_URL, params={'channel': 'c'}, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return 0
        data = resp.json()
        match_list = data.get('value', {}).get('matchInfoList', [])
        if not match_list:
            return 0

        with db_cursor() as cur:
            inserted = 0

            for info in match_list:
                for m in info.get('subMatchList', []):
                    home = m.get('homeTeamAllName', '')
                    away = m.get('awayTeamAllName', '')
                    match_num = m.get('matchNumStr', '')
                    match_date = m.get('matchDate', '')
                    match_time = m.get('matchTime', '00:00:00')
                    league = m.get('leagueAllName', m.get('leagueName', '国际赛'))

                    if not home or not away or not match_num:
                        continue

                    match_id = f'JCZQ_{match_num}_{match_date}'
                    full_time = f'{match_date} {match_time}' if match_time else match_date

                    ho = do = ao = ''
                    for pool in m.get('oddsList', []):
                        if pool.get('poolCode') == 'HAD':
                            ho, do, ao = pool.get('h', ''), pool.get('d', ''), pool.get('a', '')
                            break

                    cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time)
                        VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), match_time=VALUES(match_time)''',
                        (match_id, league, home, away, full_time))
                    inserted += 1

                    if ho and do and ao:
                        try:
                            cur.execute('''INSERT INTO odds (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening)
                                VALUES (%s,%s,%s,%s,%s,0)
                                ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds), draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)''',
                                (match_id, 'sporttery_cn', ho, do, ao))
                        except Exception as e:
                            logger.debug(f"Odds insert failed: {e}")
        return inserted
    except Exception as e:
        logger.warning(f'sporttery upcoming failed: {e}')
        return 0


def _fetch_upcoming_from_html():
    """方法2: 直接爬体彩官网HTML页面解析比赛"""
    try:
        resp = requests.get('https://www.sporttery.cn/jc/zqspf/', headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return 0
        html = resp.text

        # Parse match data from the page
        import re
        # Look for match data in the page - typical pattern in sporttery.cn
        matches = re.findall(r'data-matchid="(\d+)".*?data-homename="([^"]*).*?data-awayname="([^"]*).*?data-leaguename="([^"]*).*?data-matchnum="([^"]*).*?data-matchdate="([^"]*)', html, re.DOTALL)
        if not matches:
            # Try alternative pattern
            matches = re.findall(r'"homeTeamAllName":"([^"]*)","awayTeamAllName":"([^"]*)","leagueAllName":"([^"]*)","matchNumStr":"([^"]*)","matchDate":"([^"]*)"', html)

        if not matches:
            return 0

        with db_cursor() as cur:
            inserted = 0

            for m in matches:
                if len(m) == 6:
                    _, home, away, league, num, date = m
                elif len(m) == 5:
                    home, away, league, num, date = m
                else:
                    continue
                if not home or not away:
                    continue
                match_id = f'JCZQ_{num}_{date}'
                cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), home_team_name=VALUES(home_team_name), away_team_name=VALUES(away_team_name)''',
                    (match_id, league, home, away, date))
                inserted += 1
        return inserted
    except Exception as e:
        logger.warning(f'HTML parse failed: {e}')
        return 0


def _fetch_500_upcoming():
    """方法3: 500彩票网竞彩足球"""
    try:
        resp = requests.get('https://live.500.com/jczq.php', headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.500.com/',
        }, timeout=15)
        if resp.status_code != 200:
            return 0
        html = resp.text

        import re
        # Parse match rows from 500.com
        # Pattern: match rows with team names and match numbers
        rows = re.findall(r'<tr.*?id="tr_(\d+)".*?</tr>', html, re.DOTALL)
        if not rows:
            return 0

        with db_cursor() as cur:
            inserted = 0

            for row_html in rows[:50]:
                teams = re.findall(r'<a[^>]*>([^<]+)</a>', row_html)
                if len(teams) >= 2:
                    home = teams[0].strip()
                    away = teams[1].strip()
                    league_match = re.search(r'<td[^>]*class="[^"]*league[^"]*"[^>]*>([^<]*)<', row_html)
                    league = league_match.group(1).strip() if league_match else '未知联赛'
                    num_match = re.search(r'<td[^>]*>(\d+)</td>', row_html)
                    num = num_match.group(1) if num_match else str(inserted + 1)
                    date_match = re.search(r'<td[^>]*>(\d{4}-\d{2}-\d{2})<', row_html)
                    date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
                    match_id = f'W500_{num}_{date}'
                    cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time)
                        VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), home_team_name=VALUES(home_team_name), away_team_name=VALUES(away_team_name)''',
                        (match_id, league, home, away, date))
                    inserted += 1
        return inserted
    except Exception as e:
        logger.warning(f'500.com failed: {e}')
        return 0


def run_updater():
    """主更新函数 - 被auto_data_service调用"""
    # 1. 拉取即将开赛的比赛 + 赔率
    fetch_upcoming_matches()
    # 2. 更新已完赛的比赛结果
    updated = update_match_results(days=3)

    # 3. 只为没有预测的新比赛生成预测（已有预测的不动）
    try:
        from ml.hybrid_predictor import HybridPredictor

        with db_cursor() as cur:
            cur.execute('''SELECT m.match_id, m.league_name, m.home_team_name, m.away_team_name, m.match_time
                FROM matches m LEFT JOIN prediction_history ph ON m.match_id = ph.match_id
                WHERE ph.id IS NULL LIMIT 50''')
            new_matches = cur.fetchall()

            if new_matches:
                predictor = HybridPredictor()

                for mid, league, home, away, mtime in new_matches:
                    try:
                        match_date = mtime.strftime('%Y-%m-%d') if mtime else datetime.now().strftime('%Y-%m-%d')
                        result = predictor.predict(home, away, league)
                        cur.execute('''INSERT INTO prediction_history
                            (match_id, match_date, league, home_team, away_team,
                             prediction_result, prediction_name, confidence, is_correct)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)''',
                            (mid, match_date, league, home, away,
                             result['prediction'], result['prediction_name'],
                             result['confidence']))
                    except Exception as e:
                        logger.debug(f"Prediction failed for {mid}: {e}")

                logger.info(f'Generated predictions for {len(new_matches)} new matches')
    except Exception as e:
        logger.warning(f'Prediction generation failed: {e}')

    return updated


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    run_updater()
