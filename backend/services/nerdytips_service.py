"""Nerdytips预测数据抓取服务"""
import re, json, logging, os, time

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'nerdytips_predictions.json')


def scrape_nerdytips():
    """Selenium抓取nerdytips.com预测数据"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        logger.error("Selenium not installed")
        return []

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(30)
        driver.get('https://nerdytips.com/zh/zuqiu-tuijian')
        time.sleep(8)
        html = driver.page_source

        sections = html.split('data-match-status=')
        matches = []
        for sec in sections[1:]:
            chunk = sec[:3000]
            url_m = re.search(r"href=\"https://nerdytips\.com/zh/bisai/([^\"]+)\"", chunk)
            if not url_m:
                continue

            url = url_m.group(1)
            parts = url.split('-vs-')
            if len(parts) != 2:
                continue
            home = parts[0].replace('-', ' ').title().strip()
            away = re.sub(r'-\d+$', '', parts[1]).replace('-', ' ').title().strip()

            rating = None
            rm = re.search(r'>(\d+\.?\d*)\s*/\s*10<', chunk)
            if rm:
                rating = float(rm.group(1))

            time_m = re.search(r'>(\d{2}:\d{2})<', chunk)
            match_time = time_m.group(1) if time_m else ''

            tip_m = re.search(r"data-best-tip-validation=\"([^\"]*)\"", chunk)
            tip = tip_m.group(1) if tip_m else '1'
            tip_map = {'1': 'home', 'X': 'draw', '2': 'away'}
            prediction = tip_map.get(tip.lower(), 'home')

            matches.append({
                'home': home, 'away': away, 'time': match_time,
                'rating': rating, 'prediction': prediction,
            })

        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(matches, f, ensure_ascii=False, indent=2)
        logger.info(f"Nerdytips: scraped {len(matches)} predictions")

        return matches
    except Exception as e:
        logger.error(f"Nerdytips scrape failed: {e}")
        return []
    finally:
        if driver:
            driver.quit()


def load_cached_predictions():
    """加载缓存的nerdytips预测"""
    if os.path.exists(CACHE_FILE):
        try:
            mtime = os.path.getmtime(CACHE_FILE)
            if time.time() - mtime < 7200:  # 2小时缓存
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
    # 缓存过期或不存在, 重新抓取
    return scrape_nerdytips()


def get_nerdytips_prediction(home_cn, away_cn):
    """获取特定比赛的nerdytips预测（队名中文→英文匹配）"""
    # 队名中英对照
    name_map = {
        '皇家马德里': 'Real Madrid', '巴塞罗那': 'Barcelona',
        '马德里竞技': 'Atletico Madrid', '塞维利亚': 'Sevilla',
        '拜仁慕尼黑': 'Bayern Munich', '多特蒙德': 'Borussia Dortmund',
        '勒沃库森': 'Bayer Leverkusen', '莱比锡': 'Rb Leipzig',
        '曼城': 'Manchester City', '利物浦': 'Liverpool',
        '阿森纳': 'Arsenal', '切尔西': 'Chelsea',
        '曼联': 'Manchester United', '热刺': 'Tottenham',
        '国际米兰': 'Inter Milan', 'AC米兰': 'Ac Milan',
        '尤文图斯': 'Juventus', '那不勒斯': 'Napoli',
        '巴黎圣日耳曼': 'Paris Saint Germain', '马赛': 'Marseille',
        '摩纳哥': 'Monaco', '里昂': 'Lyon',
        '波尔图': 'Porto', '本菲卡': 'Benfica',
        '阿贾克斯': 'Ajax', '埃因霍温': 'Psv',
    }

    home_en = name_map.get(home_cn, home_cn)
    away_en = name_map.get(away_cn, away_cn)

    predictions = load_cached_predictions()
    if not predictions:
        return None

    # 模糊匹配
    for p in predictions:
        if (home_en.lower() in p['home'].lower() or p['home'].lower() in home_en.lower()) and \
           (away_en.lower() in p['away'].lower() or p['away'].lower() in away_en.lower()):
            return {
                'source': 'nerdytips',
                'prediction': p['prediction'],
                'confidence': int(p['rating'] * 10) if p['rating'] else 50,
                'rating': p['rating'],
            }

    return None
