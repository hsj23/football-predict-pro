"""
体彩官网真实数据抓取 - sporttery.cn
每次抓取最新比赛结果并更新数据库
"""
import time, re, json, logging
from datetime import datetime
from app.db_helper import db_cursor

logger = logging.getLogger(__name__)


def scrape_sporttery_results():
    """用 Selenium 抓取体彩官网赛果，返回解析后的比赛数据"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("Selenium 未安装")
        return []

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    results = []
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(30)
        driver.get('https://www.sporttery.cn/jc/zqsgkj/')
        time.sleep(10)  # 等待 JS 动态渲染完成

        html = driver.page_source
        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            texts = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            texts = [re.sub(r'\s+', ' ', t).strip() for t in texts if t.strip()]

            if len(texts) < 6:
                continue

            date = match_num = league = home = away = half_score = full_score = status = ''
            odds = []

            for t in texts:
                if re.match(r'\d{4}-\d{2}-\d{2}$', t):
                    date = t
                elif re.match(r'周[一二三四五六日]\d+', t):
                    match_num = t
                elif re.match(r'^\d+:\d+$', t):
                    if not half_score:
                        half_score = t
                    elif not full_score:
                        full_score = t
                elif re.match(r'^\d+\.\d+$', t) and len(odds) < 3:
                    odds.append(t)
                elif t in ('已完成', '已取消', '已停售', '未开始', '进行中'):
                    status = t
                elif 'VS' in t:
                    parts = t.split('VS')
                    home = re.sub(r'\([-+]\d+\)', '', parts[0]).strip()
                    away = re.sub(r'\([-+]\d+\)', '', parts[1]).strip()

            if not league:
                for i, t in enumerate(texts):
                    if 'VS' in t and i > 0:
                        league = texts[i - 1]
                        break

            # 用文本里第二个字段当联赛名 (如果上面的逻辑没找到)
            if not league and len(texts) >= 4:
                league = texts[2]

            if date and match_num:
                match_id = f"JCZQ_{match_num}_{date}"
                results.append({
                    'date': date, 'match_num': match_num, 'league': league,
                    'home': home, 'away': away,
                    'half_score': half_score, 'full_score': full_score,
                    'odds': odds, 'status': status
                })
                # 保存赔率数据到数据库
                if odds:
                    save_odds_to_db(match_id, [odds])

    except Exception as e:
        logger.error(f"抓取失败: {e}")
    finally:
        if driver:
            driver.quit()

    return results


def save_odds_to_db(match_id, odds_list):
    """将赔率数据保存到 odds 表"""
    if not odds_list:
        return
    try:
        with db_cursor() as cur:
            for is_opening in [1, 0]:
                for o in odds_list:
                    try:
                        cur.execute(
                            'INSERT INTO odds (match_id, bookmaker, home_odds, draw_odds, away_odds, '
                            'is_opening) VALUES (%s,%s,%s,%s,%s,%s)',
                            (match_id, 'sporttery_cn',
                             float(o[0]) if len(o) > 0 else None,
                             float(o[1]) if len(o) > 1 else None,
                             float(o[2]) if len(o) > 2 else None,
                             is_opening))
                    except Exception as e:
                        logger.debug(f"Odds insert failed: {e}")
        logger.info(f'Saved odds for {match_id}: {odds_list}')
    except Exception as e:
        logger.warning(f'Save odds failed: {e}')


def update_database_with_results(results):
    """将真实赛果更新到 prediction_history 和 matches 表"""
    try:
        with db_cursor() as cur:
            updated_pred = 0
            updated_match = 0
            for r in results:
                if not r.get('full_score'):
                    continue

                match_id = f"JCZQ_{r['match_num']}_{r['date']}"
                try:
                    fs_parts = r['full_score'].split(':')
                    home_score = int(fs_parts[0])
                    away_score = int(fs_parts[1])
                except (ValueError, IndexError):
                    continue

                if home_score > away_score:
                    actual = 'home'
                elif home_score < away_score:
                    actual = 'away'
                else:
                    actual = 'draw'

                actual_score = f'{home_score}-{away_score}'

                cur.execute(
                    'UPDATE matches SET status=%s, home_score=%s, away_score=%s WHERE match_id=%s',
                    ('finished', home_score, away_score, match_id))
                if cur.rowcount > 0:
                    updated_match += 1

                cur.execute(
                    'SELECT id, prediction_result FROM prediction_history WHERE match_id=%s',
                    (match_id,))
                row = cur.fetchone()
                if row:
                    is_correct = 1 if row[1] == actual else 2
                    cur.execute(
                        'UPDATE prediction_history SET actual_result=%s, actual_score=%s, '
                        'home_score=%s, away_score=%s, is_correct=%s WHERE match_id=%s',
                        (actual, actual_score, home_score, away_score, is_correct, match_id))
                    updated_pred += 1
                else:
                    cur.execute(
                        'INSERT INTO prediction_history '
                        '(match_id, match_date, league, home_team, away_team, '
                        'prediction_result, prediction_name, confidence, '
                        'actual_result, actual_score, home_score, away_score, is_correct) '
                        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (match_id, r['date'], r['league'], r['home'], r['away'],
                         'home', '主胜', 50, actual,
                         actual_score, home_score, away_score, 0))

            print(f"  更新 matches: {updated_match} 场, prediction_history: {updated_pred} 场")
            return updated_match + updated_pred
    except Exception as e:
        logger.error(f"数据库更新失败: {e}")
        return 0


def get_today_matches_from_db():
    """从数据库获取今日比赛列表"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        with db_cursor() as cur:
            cur.execute(
                'SELECT match_id, league_name, home_team_name, away_team_name, match_time '
                'FROM matches WHERE match_time >= %s ORDER BY match_time LIMIT 30',
                (today,))
            rows = cur.fetchall()
        return [{'match_id': r[0], 'league': r[1], 'home': r[2], 'away': r[3],
                 'time': str(r[4])} for r in rows]
    except Exception as e:
        logger.debug(f"DB query failed: {e}")
        return []


def scrape_upcoming_matches():
    """抓取足彩官网即将开赛的比赛（对阵表）"""
    results = []
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("Selenium 未安装")
        return results

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        # 足彩网竞彩对阵页面
        driver.get('https://www.sporttery.cn/jc/zqdz/')
        time.sleep(8)
        html = driver.page_source

        trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        today_str = datetime.now().strftime('%Y-%m-%d')

        for tr in trs:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
            texts = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
            texts = [re.sub(r'\s+', ' ', t).strip() for t in texts if t.strip()]

            date = match_num = league = home = away = odds_str = ''
            odds = []
            for t in texts:
                if re.match(r'\d{4}-\d{2}-\d{2}$', t):
                    date = t
                elif re.match(r'周[一二三四五六日]\d+', t):
                    match_num = t
                elif re.match(r'^\d+\.\d+$', t) and len(odds) < 3:
                    odds.append(t)
                elif 'VS' in t or 'vs' in t:
                    parts = re.split(r'\s*(?:VS|vs)\s*', t)
                    if len(parts) == 2:
                        home = re.sub(r'\([-+]\d+\)', '', parts[0]).strip()
                        away = re.sub(r'\([-+]\d+\)', '', parts[1]).strip()

            if not date:
                date = today_str

            if match_num and home and away:
                match_id = f"JCZQ_{match_num}_{date}"
                results.append({
                    'match_id': match_id, 'date': date, 'match_num': match_num,
                    'league': league, 'home': home, 'away': away,
                    'odds': odds, 'status': 'scheduled'
                })
                if odds:
                    save_odds_to_db(match_id, [odds])
    except Exception as e:
        logger.warning(f"Scrape upcoming matches failed: {e}")
    finally:
        if driver:
            driver.quit()
    return results


def save_upcoming_to_db(matches_data):
    """将即将开赛的比赛存入 matches 表"""
    if not matches_data:
        return 0
    try:
        saved = 0
        with db_cursor() as cur:
            for m in matches_data:
                try:
                    cur.execute(
                        'INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, '
                        'match_time, status) VALUES (%s,%s,%s,%s,%s,%s) '
                        'ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), '
                        'status=VALUES(status)',
                        (m['match_id'], m.get('league', ''), m['home'], m['away'],
                         m['date'] + ' 00:00:00', m.get('status', 'scheduled')))
                    saved += 1
                except Exception as e:
                    logger.debug(f"Save match failed: {e}")
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Saved {saved} upcoming matches to DB")
        return saved
    except Exception as e:
        logger.warning(f"Save upcoming matches failed: {e}")
        return 0


def run_full_update():
    """完整数据更新流程"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 抓取体彩官网最新赛果...")
    results = scrape_sporttery_results()
    if results:
        with_score = [r for r in results if r.get('full_score')]
        print(f"  抓取 {len(results)} 场, 其中 {len(with_score)} 场已有比分")
        total = update_database_with_results(results)
        return results
    else:
        print("  抓取失败")
        return []
