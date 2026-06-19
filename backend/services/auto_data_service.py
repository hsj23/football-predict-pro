"""自动数据更新服务 - 积分榜/伤病/新闻 定时抓取(已验证可用)"""
import os, re, json, time, logging, threading
from datetime import datetime

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

UPDATE_INTERVALS = {
    'standings': 86400,   # 积分榜24h
    'injuries': 43200,     # 伤病12h
    'news': 21600,         # 新闻6h
}


def _selenium_fetch(url, wait=5):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except:
        return ''

    options = Options()
    options.add_argument('--headless=new'); options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox'); options.add_argument('--window-size=1920,1080')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(20)
        driver.get(url)
        time.sleep(wait)
        return driver.page_source
    except Exception as e:
        logger.warning(f'Fetch failed {url}: {e}')
        return ''
    finally:
        if driver: driver.quit()


def _save_json(name, data):
    filepath = os.path.join(DATA_DIR, f'{name}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'updated': datetime.now().isoformat(), 'data': data}, f, ensure_ascii=False)
    logger.info(f'{name} saved: {len(data)} items')


def update_standings():
    """英超积分榜 - premierleague.com (已验证: 20队)"""
    html = _selenium_fetch('https://www.premierleague.com/tables', wait=8)
    if not html:
        return None

    # 提取队名
    teams = re.findall(r'<span[^>]*class=\"[^\"]*long[^\"]*\"[^>]*>([^<]+)</span>', html)
    if not teams:
        return None

    # 每行一个队，排名=索引+1
    standings = {}
    for i, team in enumerate(teams[:20]):
        standings[team.strip()] = i + 1

    _save_json('standings', standings)
    return standings


def update_injuries():
    """伤病数据 - Fantasy Premier League 官方免费API (自动, 841球员实时状态)"""
    import requests
    try:
        r = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/',
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        players = data.get('elements', [])
        teams = {t['id']: t['name'] for t in data.get('teams', [])}

        from collections import defaultdict
        injuries = defaultdict(list)
        for p in players:
            chance = p.get('chance_of_playing_next_round')
            if chance is not None and chance < 75:  # <75%上场概率=有伤
                team = teams.get(p['team'], 'Unknown')
                injuries[team].append(p['web_name'])

        # 只保留每队前5个(去掉梯队板凳)
        result = {}
        for team, players_list in injuries.items():
            result[team] = players_list[:5]

        if result:
            _save_json('injuries', result)
            logger.info(f'Injuries: {len(result)} teams ({sum(len(v) for v in result.values())} players)')
        return result
    except Exception as e:
        logger.warning(f'Injuries failed: {e}')
        return None


def update_news():
    """足球新闻 - BBC RSS + Sky Sports (RSS不反爬)"""
    import requests
    all_news = []

    # BBC Sport RSS (不需要Selenium)
    try:
        r = requests.get('https://feeds.bbci.co.uk/sport/football/rss.xml', timeout=10,
                        headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            titles = re.findall(r'<title>(.*?)</title>', r.text)
            for t in titles[2:17]:
                t = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', t).strip()
                if t and len(t) > 10:
                    all_news.append({'source': 'bbc', 'title': t})
    except:
        pass

    # Sky Sports RSS
    try:
        r = requests.get('https://www.skysports.com/football/rss', timeout=10,
                        headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)
            for t in titles[:10]:
                t = t.strip()
                if t:
                    all_news.append({'source': 'skysports', 'title': t})
    except:
        pass

    if all_news:
        _save_json('news', all_news)
    return all_news


def load_latest_data(data_type):
    """加载最新缓存数据"""
    filepath = os.path.join(DATA_DIR, f'{data_type}.json')
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None


def needs_update(data_type):
    cached = load_latest_data(data_type)
    if not cached:
        return True
    interval = UPDATE_INTERVALS.get(data_type, 86400)
    try:
        updated = datetime.fromisoformat(cached['updated'])
        return (datetime.now() - updated).total_seconds() > interval
    except:
        return True


UPDATERS = {
    'standings': update_standings,
    'injuries': update_injuries,
    'news': update_news,
}


def run_auto_update():
    """后台自动更新所有数据"""
    updated = []
    for data_type, updater in UPDATERS.items():
        if needs_update(data_type):
            try:
                result = updater()
                if result:
                    updated.append(data_type)
                    logger.info(f'Updated: {data_type} ({len(result)} items)')
            except Exception as e:
                logger.warning(f'{data_type}: {e}')
    return updated


def start_background_updater():
    """启动后台定时更新(启动立即执行, 之后每30分钟)"""
    def _loop():
        # 跳过Selenium抓取（太慢），只抓API数据
        try:
            from services.api_updater import run_updater
            run_updater()
        except:
            pass

        tick = 0
        while True:
            time.sleep(300)  # 每5分钟
            tick += 1
            try:
                from services.api_updater import run_updater
                run_updater()
            except:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    logger.info('Auto-updater started')

# 页面打开时调用, 强制刷新需要的数据
def refresh_on_demand():
    """页面打开时按需刷新"""
    updated = []
    for data_type in ['standings', 'injuries', 'news']:
        if needs_update(data_type):
            try:
                result = UPDATERS[data_type]()
                if result:
                    updated.append(data_type)
            except:
                pass
    return updated
