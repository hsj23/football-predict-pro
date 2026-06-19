"""
爬取真实球员数据 — 从 fbref.com 获取国际比赛球员进球/助攻
运行: py scripts/scrape_players.py
"""
import requests, json, re, os, logging, time
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def scrape_international_goal_scorers():
    """
    从 fbref 爬取国家队近期比赛的进球者数据
    目标: 获取球员名、国家队、进球数
    """
    # 2026世界杯预选赛/国家联赛等国际赛事页面
    urls = [
        'https://fbref.com/en/comps/218/2026/2026-FIFA-World-Cup-qualification-Stats',
        'https://fbref.com/en/comps/570/2025-2026/UEFA-Nations-League-Stats',
    ]

    players = []
    for url in urls:
        try:
            logger.info(f'Fetching {url}...')
            resp = requests.get(url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')

            # fbref player stats table
            table = soup.find('table', id='stats_standard')
            if not table:
                table = soup.find('table', class_=re.compile('stats_table'))
            if not table:
                logger.warning(f'No table found on {url}')
                continue

            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 10:
                    continue
                try:
                    name_el = row.find('th')
                    name = name_el.text.strip() if name_el else ''
                    nation_el = cells[0].find('a')
                    nation = nation_el.text.strip() if nation_el else ''
                    goals = cells[5].text.strip() if len(cells) > 5 else '0'
                    assists = cells[6].text.strip() if len(cells) > 6 else '0'
                    if name and nation:
                        players.append({
                            'name': name,
                            'team': nation,
                            'goals': int(goals) if goals.isdigit() else 0,
                            'assists': int(assists) if assists.isdigit() else 0,
                            'position': cells[2].text.strip() if len(cells) > 2 else '?',
                            'market_value_m': 0,  # fbref doesn't have market values
                            'source': 'fbref',
                        })
                except:
                    continue

            logger.info(f'  Got {len(players)} players so far')
            time.sleep(3)
        except Exception as e:
            logger.warning(f'Failed {url}: {e}')

    if players:
        path = os.path.join(DATA_DIR, 'players.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(players, f, ensure_ascii=False, indent=2)
        logger.info(f'Saved {len(players)} players to {path}')
    else:
        logger.warning('No players scraped — fbref may have changed layout or blocked access')

    return players


if __name__ == '__main__':
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error('需要安装: pip install beautifulsoup4')
        exit(1)

    scrape_international_goal_scorers()
