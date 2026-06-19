"""
完整球员数据采集 — 支持代理
数据源: Transfermarkt (身价) + fbref (进球/助攻)
运行: py scripts/scrape_players_full.py
代理配置: 设置环境变量 HTTP_PROXY / HTTPS_PROXY
"""
import requests, json, re, os, logging, time, sys
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')

PROXY = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
PROXIES = {'http': PROXY, 'https': PROXY} if PROXY else None

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

if PROXY:
    logger.info(f'使用代理: {PROXY}')


def scrape_transfermarkt_international():
    """爬取 Transfermarkt 国际球队球员身价"""
    # 当前热门国际球队的Transfermarkt页面
    teams = {
        '挪威': 'https://www.transfermarkt.com/norway/startseite/verein/3440',
        '瑞典': 'https://www.transfermarkt.com/sweden/startseite/verein/3557',
        '土耳其': 'https://www.transfermarkt.com/turkey/startseite/verein/3384',
        '奥地利': 'https://www.transfermarkt.com/austria/startseite/verein/3338',
        '加拿大': 'https://www.transfermarkt.com/canada/startseite/verein/3510',
        '哥伦比亚': 'https://www.transfermarkt.com/colombia/startseite/verein/3816',
        '保加利亚': 'https://www.transfermarkt.com/bulgaria/startseite/verein/3374',
        '黑山': 'https://www.transfermarkt.com/montenegro/startseite/verein/5315',
        '北马其顿': 'https://www.transfermarkt.com/north-macedonia/startseite/verein/5313',
        '突尼斯': 'https://www.transfermarkt.com/tunisia/startseite/verein/3670',
        '哥斯达黎加': 'https://www.transfermarkt.com/costa-rica/startseite/verein/8497',
        '乌兹别克斯坦': 'https://www.transfermarkt.com/uzbekistan/startseite/verein/4717',
    }

    players = []
    for team, url in teams.items():
        try:
            logger.info(f'Fetching {team}...')
            resp = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=30)
            if resp.status_code != 200:
                logger.warning(f'  HTTP {resp.status_code}')
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', class_='items')
            if not table:
                logger.warning(f'  No player table found')
                continue

            for row in table.find_all('tr')[1:]:  # skip header
                cells = row.find_all('td')
                if len(cells) < 6:
                    continue
                try:
                    # Name from the first link in the row
                    name_link = row.find('a', href=re.compile('/profil/'))
                    name = name_link.text.strip() if name_link else ''
                    # Market value from cell with 'rechts hauptlink' class or containing €
                    value_cell = row.find('td', class_=re.compile('rechts'))
                    value_text = value_cell.text.strip() if value_cell else ''
                    value_m = 0
                    if 'm' in value_text:
                        value_m = float(re.sub(r'[^\d.]', '', value_text.split('m')[0]))
                    elif 'k' in value_text:
                        value_m = float(re.sub(r'[^\d.]', '', value_text.split('k')[0])) / 1000

                    if name and value_m > 0:
                        players.append({
                            'name': name,
                            'team': team,
                            'market_value_m': round(value_m, 1),
                            'position': cells[1].text.strip() if len(cells) > 1 else '?',
                            'goals': 0,
                            'assists': 0,
                            'source': 'transfermarkt',
                        })
                except:
                    continue

            cnt = sum(1 for p in players if p['team'] == team)
            logger.info(f'  Got {cnt} players for {team}')
            time.sleep(2)  # 礼貌间隔
        except Exception as e:
            logger.warning(f'  {team}: {e}')

    return players


def scrape_fbref_stats():
    """爬取 fbref 球员进球助攻数据"""
    # 2026世界杯预选赛统计
    urls = [
        'https://fbref.com/en/comps/218/stats/2026-FIFA-World-Cup-qualification-Stats',
        'https://fbref.com/en/comps/570/stats/2025-2026-UEFA-Nations-League-Stats',
    ]

    stats = {}
    for url in urls:
        try:
            logger.info(f'Fetching fbref stats...')
            resp = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=30)
            if resp.status_code != 200:
                logger.warning(f'  HTTP {resp.status_code}')
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            # fbref uses multiple table IDs
            for tid in ['stats_standard', 'stats_standard_dom_lg']:
                table = soup.find('table', id=tid)
                if not table:
                    table = soup.find('table', class_=re.compile('stats_table'))
                if not table:
                    continue

                for row in table.find_all('tr'):
                    try:
                        name_el = row.find('th', {'data-stat': 'player'})
                        if not name_el:
                            continue
                        name = name_el.text.strip()
                        cells = row.find_all('td')
                        if len(cells) < 8:
                            continue
                        goals = cells[5].text.strip() if len(cells) > 5 else '0'
                        assists = cells[6].text.strip() if len(cells) > 6 else '0'
                        if name:
                            stats[name] = {
                                'goals': int(float(goals)) if goals.replace('.','').isdigit() else 0,
                                'assists': int(float(assists)) if assists.replace('.','').isdigit() else 0,
                            }
                    except:
                        continue

                logger.info(f'  Got {len(stats)} player stats from {tid}')
                break
            time.sleep(3)
        except Exception as e:
            logger.warning(f'  {url}: {e}')

    return stats


def merge_and_save(players, stats):
    """合并身价和进球数据"""
    for p in players:
        if p['name'] in stats:
            p['goals'] = stats[p['name']]['goals']
            p['assists'] = stats[p['name']]['assists']

    # 也保存纯fbref数据（没有被transfermarkt覆盖的）
    existing_names = {p['name'] for p in players}
    for name, s in stats.items():
        if name not in existing_names:
            players.append({
                'name': name,
                'team': '',
                'market_value_m': 0,
                'position': '?',
                'goals': s['goals'],
                'assists': s['assists'],
                'source': 'fbref',
            })

    path = os.path.join(DATA_DIR, 'players.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
    logger.info(f'保存 {len(players)} 球员到 {path}')
    return players


if __name__ == '__main__':
    if not PROXY:
        logger.warning('未检测到代理。如果需要翻墙，请设置: set HTTPS_PROXY=http://127.0.0.1:xxxx')
        logger.warning('直接尝试连接...')

    # Step 1: Transfermarkt 身价
    players = scrape_transfermarkt_international()
    logger.info(f'Transfermarkt: {len(players)} 球员')

    # Step 2: fbref 进球助攻
    stats = scrape_fbref_stats()
    logger.info(f'fbref: {len(stats)} 球员统计')

    # Step 3: 合并保存
    if players or stats:
        merge_and_save(players, stats)
    else:
        logger.error('没有获取到任何数据。请设置代理后重试。')
