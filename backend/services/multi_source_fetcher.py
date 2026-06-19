"""
多源真实数据抓取器 — 多种反反爬策略
策略: 轮换UA/Referer → 移动端API → JSON端点 → Selenium最后手段
"""
import os, re, json, time, logging, random, hashlib, gzip, io
from datetime import datetime

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

# 轮换User-Agent池
UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
]

# 代理配置
PROXY_URL = os.environ.get('HTTP_PROXY', 'http://127.0.0.1:7892')

# The Odds API 配置
ODDS_API_KEY = '63e6c2103ea9f9a8fe8509f2add255b0'
ODDS_API_BASE = 'https://api.the-odds-api.com/v4'

# OddsPapi 备用配置（免费，350+博彩公司）
ODDSPAPI_BASE = 'https://api.oddspapi.io/v3'
ODDSPAPI_KEY = os.environ.get('ODDSPAPI_KEY', '')  # 需要注册获取

# 足球联赛映射 (竞彩联赛 → OddsAPI sport key)
LEAGUE_TO_ODDS_SPORT = {
    '英超': 'soccer_england_premier_league',
    '西甲': 'soccer_spain_la_liga',
    '德甲': 'soccer_germany_bundesliga',
    '意甲': 'soccer_italy_serie_a',
    '法甲': 'soccer_france_ligue_one',
    '欧冠': 'soccer_uefa_champions_league',
    '欧联杯': 'soccer_uefa_europa_league',
    '英冠': 'soccer_england_championship',
    '荷甲': 'soccer_netherlands_eredivisie',
    '葡超': 'soccer_portugal_primeira_liga',
    '巴甲': 'soccer_brazil_campeonato',
    '阿甲': 'soccer_argentina_primera_division',
    '美职联': 'soccer_usa_mls',
    '日职': 'soccer_japan_j_league',
    '韩K联': 'soccer_korea_kleague1',
    '澳超': 'soccer_australia_aleague',
    '中超': 'soccer_china_superleague',
    '国际赛': 'soccer_uefa_nations_league',  # 国际友谊赛/欧国联
    '世界杯': 'soccer_fifa_world_cup',
    '欧洲杯': 'soccer_uefa_euro',
}

CACHE = {}
CACHE_LOCK = __import__('threading').Lock()
CACHE_TTL = 1800


# ═══════════════════════════════════════════════
#  0. The Odds API — 真实国际博彩赔率（备用：OddsPapi）
# ═══════════════════════════════════════════════

_odds_api_cache = {}
_odds_api_cache_time = 0

def fetch_odds_api_odds(league_name='英超'):
    """从The Odds API获取真实博彩赔率 — 免费500 credits/月，失败时用OddsPapi"""
    import urllib.request, json as jx, gzip as gz

    sport_key = LEAGUE_TO_ODDS_SPORT.get(league_name, 'soccer_uefa_nations_league')
    
    # 主数据源：The Odds API
    url = f'{ODDS_API_BASE}/sports/{sport_key}/odds/?apiKey={ODDS_API_KEY}&regions=uk,eu&markets=h2h,spreads,totals&oddsFormat=decimal'
    
    try:
        proxy_handler = urllib.request.ProxyHandler({'http': PROXY_URL, 'https': PROXY_URL}) if PROXY_URL else None
        opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()
        req = urllib.request.Request(url, headers={'User-Agent': 'FootballPredict/1.0', 'Accept': 'application/json'})
        with opener.open(req, timeout=15) as resp:
            raw = resp.read()
            if resp.headers.get('Content-Encoding') == 'gzip':
                raw = gz.decompress(raw)
            # 检查剩余credits
            remaining = resp.headers.get('x-requests-remaining', '?')
            logger.info(f'Odds API: {resp.status}, credits remaining: {remaining}')
            data = jx.loads(raw.decode('utf-8'))
            return data
    except Exception as e:
        logger.warning(f'Odds API failed: {e}, trying OddsPapi fallback...')
        # 备用：OddsPapi
        return _fetch_oddspapi(sport_key)


def _fetch_oddspapi(sport_key):
    """备用数据源：OddsPapi（免费，350+博彩公司）"""
    import urllib.request, json as jx
    
    if not ODDSPAPI_KEY:
        logger.debug('OddsPapi key not configured, skipping')
        return []
    
    url = f'{ODDSPAPI_BASE}/odds?sport={sport_key}&apiKey={ODDSPAPI_KEY}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'FootballPredict/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = jx.loads(resp.read().decode('utf-8'))
            logger.info(f'OddsPapi: fetched {len(data)} matches')
            return data
    except Exception as e:
        logger.debug(f'OddsPapi failed: {e}')
        return []


def get_odds_api_predictions(home_team, away_team, league_name='国际赛'):
    """从Odds API获取某场比赛的各博彩公司预测（含让球盘+大小球）"""
    global _odds_api_cache, _odds_api_cache_time

    # 10分钟缓存
    now = time.time()
    cache_key = league_name
    if cache_key in _odds_api_cache and now - _odds_api_cache_time < 600:
        data = _odds_api_cache[cache_key]
    else:
        data = fetch_odds_api_odds(league_name)
        _odds_api_cache = {cache_key: data}
        _odds_api_cache_time = now

    if not data:
        return []

    results = []
    for match in data:
        mh = match.get('home_team', '')
        ma = match.get('away_team', '')
        # 模糊匹配队名
        if not _match_teams(home_team, away_team, mh, ma):
            continue

        bookmakers = match.get('bookmakers', [])
        for bm in bookmakers[:12]:  # 最多12家
            bm_name = bm.get('title', '')
            markets = bm.get('markets', [])

            ho = do = ao = None
            handicap = None       # 让球数
            handicap_odds = None  # 让球赔率
            over_line = None      # 大小球盘口
            over_odds = None      # 大球赔率
            under_odds = None     # 小球赔率

            for market in markets:
                mkey = market.get('key', '')
                outcomes = market.get('outcomes', [])

                if mkey == 'h2h' and len(outcomes) >= 3:
                    for o in outcomes:
                        if o['name'] == mh: ho = o['price']
                        elif o['name'] == ma: ao = o['price']
                        elif o['name'] == 'Draw': do = o['price']

                elif mkey == 'spreads' and len(outcomes) >= 2:
                    # 让球盘: home favorite gets negative point spread
                    for o in outcomes:
                        if o['name'] == mh:
                            handicap = o.get('point', 0)
                            handicap_odds = o.get('price', 0)

                elif mkey == 'totals' and len(outcomes) >= 2:
                    for o in outcomes:
                        over_line = o.get('point', 2.5)
                        if o['name'] == 'Over':
                            over_odds = o.get('price', 0)
                        elif o['name'] == 'Under':
                            under_odds = o.get('price', 0)

            if ho and do and ao:
                total = 1/ho + 1/do + 1/ao
                hp = round(1/ho / total * 100, 1)
                dp = round(1/do / total * 100, 1)
                ap = round(1/ao / total * 100, 1)
                best = max([('home', hp), ('draw', dp), ('away', ap)], key=lambda x: x[1])
                conf = min(75, max(30, best[1] + 5))

                # 理由
                reasons = []
                if ho < 2.0: reasons.append(f'{bm_name}: 主胜低赔({ho})，市场看好')
                if do < 3.5: reasons.append(f'{bm_name}: 平赔偏低({do})')
                if ao < 2.5: reasons.append(f'{bm_name}: 客胜赔付合理')
                if abs(ho - ao) < 0.3: reasons.append(f'{bm_name}: 赔率接近，实力均衡')
                # 让球盘分析
                if handicap is not None:
                    if handicap < 0: reasons.append(f'{bm_name}: 让球{handicap}，看好主队')
                    elif handicap > 0: reasons.append(f'{bm_name}: 让球+{handicap}，看好客队')
                    else: reasons.append(f'{bm_name}: 平手盘')
                # 大小球分析
                if over_line is not None and over_odds is not None:
                    if over_odds < 1.8: reasons.append(f'{bm_name}: 大{over_line}球低赔，看好进球多')
                    elif under_odds and under_odds < 1.8: reasons.append(f'{bm_name}: 小{over_line}球低赔，看好进球少')
                if not reasons: reasons.append(f'{bm_name}: 市场无明确倾向')

                result = {
                    'platform': bm_name,
                    'prediction': best[0],
                    'confidence': conf,
                    'style': f'国际赔率 (返还率{round((1-total)*100,1)}%)',
                    'reasons': reasons,
                    'odds': {'home': round(ho, 2), 'draw': round(do, 2), 'away': round(ao, 2)},
                    'data_source': 'real',
                }
                if handicap is not None:
                    result['handicap'] = handicap
                    result['handicap_odds'] = handicap_odds
                if over_line is not None:
                    result['over_under_line'] = over_line
                    result['over_odds'] = over_odds
                    result['under_odds'] = under_odds
                results.append(result)

    logger.info(f'Odds API: found {len(results)} bookmakers for {home_team} vs {away_team}')
    return results


def get_odds_api_handicap_totals(home_team, away_team, league_name='国际赛'):
    """从Odds API获取某场比赛的平均让球盘和大小球数据（用于特征工程）"""
    predictions = get_odds_api_predictions(home_team, away_team, league_name)
    if not predictions:
        return None

    handicaps = []
    handicap_odds_list = []
    over_lines = []
    over_odds_list = []
    under_odds_list = []

    for p in predictions:
        if 'handicap' in p:
            handicaps.append(p['handicap'])
            handicap_odds_list.append(p.get('handicap_odds', 0))
        if 'over_under_line' in p:
            over_lines.append(p['over_under_line'])
            over_odds_list.append(p.get('over_odds', 0))
            under_odds_list.append(p.get('under_odds', 0))

    result = {}
    if handicaps:
        result['avg_handicap'] = round(sum(handicaps) / len(handicaps), 2)
        result['handicap_count'] = len(handicaps)
        if handicap_odds_list:
            valid = [x for x in handicap_odds_list if x > 0]
            if valid:
                result['avg_handicap_home_odds'] = round(sum(valid) / len(valid), 2)
    if over_lines:
        result['avg_over_line'] = round(sum(over_lines) / len(over_lines), 2)
        valid_over = [x for x in over_odds_list if x > 0]
        valid_under = [x for x in under_odds_list if x > 0]
        if valid_over:
            result['avg_over_odds'] = round(sum(valid_over) / len(valid_over), 2)
        if valid_under:
            result['avg_under_odds'] = round(sum(valid_under) / len(valid_under), 2)
        result['over_under_count'] = len(over_lines)

    return result if result else None


def _smart_fetch(url, headers=None, timeout=15, encoding='utf-8', retry=3, method='GET', data=None, use_proxy=True):
    """智能HTTP抓取 — 自动重试 + UA轮换 + 代理支持 + 反限流"""
    import urllib.request, urllib.error, ssl, time as _time

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    # 配置代理（多代理轮换）
    proxy_handlers = []
    if use_proxy and PROXY_URL:
        proxy_handlers.append(urllib.request.ProxyHandler({'http': PROXY_URL, 'https': PROXY_URL}))

    for attempt in range(retry + 1):
        # 随机延迟（反限流）
        if attempt > 0:
            delay = random.uniform(2, 5) * attempt
            _time.sleep(delay)
        
        ua = random.choice(UA_POOL)
        req_headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Google Chrome";v="120"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Connection': 'keep-alive',
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers, data=data.encode() if data else None, method=method)
        opener = urllib.request.build_opener(*proxy_handlers) if proxy_handlers else urllib.request.build_opener()
        try:
            with opener.open(req, timeout=timeout, context=ssl_ctx) as resp:
                raw = resp.read()
                ce = resp.headers.get('Content-Encoding', '')
                if 'gzip' in ce:
                    raw = gzip.decompress(raw)
                return raw.decode(encoding, errors='ignore')
        except urllib.error.HTTPError as e:
            if attempt < retry:
                time.sleep(1 + attempt)
                continue
            logger.debug(f'HTTP {e.code} for {url}')
            return None
        except Exception as e:
            if attempt < retry:
                time.sleep(1 + attempt)
                continue
            logger.debug(f'Fetch failed {url}: {e}')
            return None
    return None


# ═══════════════════════════════════════════════
#  1. Forebet — 尝试多种端点
# ═══════════════════════════════════════════════

# Forebet 缓存（每30分钟最多请求一次）
_forebet_cache = None
_forebet_cache_time = 0

def _fetch_forebet():
    """抓取Forebet今日预测 — 带限流保护和反检测"""
    global _forebet_cache, _forebet_cache_time
    now = time.time()
    # 增加缓存时间到60分钟（避免频繁请求）
    if _forebet_cache is not None and now - _forebet_cache_time < 3600:
        return _forebet_cache

    results = []
    
    # 尝试多个Forebet域名（反封禁）
    forebet_urls = [
        'https://forebet.com/en/football-tips-and-predictions-for-today',
        'https://www.forebet.com/en/football-tips-and-predictions-for-today',
    ]
    
    for url in forebet_urls:
        html = _smart_fetch(url,
                            headers={
                                'Referer': 'https://www.google.com/',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'Sec-Fetch-Site': 'cross-site',
                            },
                            use_proxy=True, timeout=25, retry=3)
        if html:
            break
        # 切换域名前等待
        time.sleep(random.uniform(3, 6))
    
    if not html:
        logger.warning('Forebet fetch failed (all attempts)')
        return _forebet_cache or []  # 返回旧缓存

    # 更新缓存
    _forebet_cache_time = now

    if html:
        # 解析预测表格
        # Forebet结构: <div class="rcnt"> 包含主客队和预测
        blocks = re.findall(r'class="rn_[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
        if not blocks:
            # 备选匹配
            blocks = re.findall(r'<span class="homeTeam[^"]*">([^<]+)</span>.*?<span class="awayTeam[^"]*">([^<]+)</span>.*?class="fprc[^"]*"[^>]*>(\d+)%<.*?class="fprc[^"]*"[^>]*>(\d+)%<.*?class="fprc[^"]*"[^>]*>(\d+)%<', html, re.DOTALL)
            if blocks:
                for h, a, hp, dp, ap in blocks[:50]:
                    probs = {'home': int(hp), 'draw': int(dp), 'away': int(ap)}
                    best = max(probs, key=probs.get)
                    results.append({'home': h.strip(), 'away': a.strip(), 'prediction': best, 'source': 'Forebet'})

        if not results:
            # 策略C: match_show 类
            matches = re.findall(r'<a[^>]*class="match_show[^"]*"[^>]*href="[^"]*">([^<]+)</a>', html)
            teams = re.findall(r'<span class="homeTeam[^"]*">([^<]+)</span>.*?<span class="awayTeam[^"]*">([^<]+)</span>', html, re.DOTALL)
            preds = re.findall(r'class="forecast[^"]*"[^>]*>\s*([^\s<]+)', html)
            for i, (h, a) in enumerate(teams[:50]):
                pred = preds[i] if i < len(preds) else '1'
                pmap = {'1': 'home', 'X': 'draw', '2': 'away', '1X': 'home', 'X2': 'away'}
                results.append({'home': h.strip(), 'away': a.strip(), 'prediction': pmap.get(pred, 'home'), 'source': 'Forebet'})

    if results:
        logger.info(f'Forebet: {len(results)} predictions')
    return results


# ═══════════════════════════════════════════════
#  2. BetExplorer — 免费赔率对比
# ═══════════════════════════════════════════════

def _fetch_betexplorer():
    """从BetExplorer获取赔率对比"""
    results = []
    html = _smart_fetch('https://www.betexplorer.com/next/soccer/',
                        headers={'Referer': 'https://www.betexplorer.com/'})
    if html:
        # 解析比赛和赔率
        rows = re.findall(r'<tr[^>]*data-def="\d+-\d+-\d+-\d+"[^>]*>(.*?)</tr>', html, re.DOTALL)
        for row in rows[:50]:
            teams = re.findall(r'<span[^>]*class="[^"]*wrap[^"]*"[^>]*>([^<]+)</span>', row)
            odds = re.findall(r'data-odd="([\d.]+)"', row)
            if len(teams) >= 2 and len(odds) >= 3:
                try:
                    ho, do, ao = float(odds[0]), float(odds[1]), float(odds[2])
                    results.append({
                        'home': teams[0].strip(), 'away': teams[1].strip(),
                        'odds': {'home': ho, 'draw': do, 'away': ao},
                        'source': 'BetExplorer',
                        'bookmaker': '平均赔率',
                    })
                except: pass
        logger.info(f'BetExplorer: {len(results)} matches with odds')
    return results


# ═══════════════════════════════════════════════
#  3. FlashScore — 实时数据
# ═══════════════════════════════════════════════

def _fetch_flashscore(date=None):
    """从FlashScore获取比赛和赔率"""
    if not date:
        date = datetime.now().strftime('%Y-%m-%d')
    # FlashScore内部API
    url = f'https://www.flashscore.com/football/{date}/'
    html = _smart_fetch(url, headers={'Referer': 'https://www.flashscore.com/', 'X-Requested-With': 'XMLHttpRequest'})
    if not html:
        return []

    results = []
    # FlashScore在页面嵌入JSON数据
    json_match = re.search(r'window\.__data\s*=\s*(\{.*?\});', html, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            # 递归查找比赛数据
            def find_matches(obj, depth=0):
                if depth > 5: return
                if isinstance(obj, dict):
                    if 'homeName' in obj and 'awayName' in obj:
                        odds = obj.get('odds', {})
                        results.append({
                            'home': obj.get('homeName', ''),
                            'away': obj.get('awayName', ''),
                            'odds': odds,
                            'source': 'FlashScore',
                        })
                    for v in obj.values():
                        find_matches(v, depth+1)
                elif isinstance(obj, list):
                    for item in obj:
                        find_matches(item, depth+1)
            find_matches(data)
        except:
            pass

    if results:
        logger.info(f'FlashScore: {len(results)} matches')
    return results


# ═══════════════════════════════════════════════
#  4. 综合：获取所有真实数据
# ═══════════════════════════════════════════════

def _match_teams(home1, away1, home2, away2):
    """模糊匹配两个队名是否指同一场比赛"""
    h1 = re.sub(r'[^a-zA-Z一-鿿]', '', home1.lower())
    a1 = re.sub(r'[^a-zA-Z一-鿿]', '', away1.lower())
    h2 = re.sub(r'[^a-zA-Z一-鿿]', '', home2.lower())
    a2 = re.sub(r'[^a-zA-Z一-鿿]', '', away2.lower())
    return (h1 in h2 or h2 in h1) and (a1 in a2 or a2 in a1)


def get_real_bookmaker_predictions(match_id, home_team, away_team, league_name='国际赛'):
    """获取所有博彩公司的真实赔率预测"""
    results = []

    # 1. The Odds API — 国际博彩公司（优先级最高）
    try:
        odds_api_results = get_odds_api_predictions(home_team, away_team, league_name)
        results.extend(odds_api_results)
        if odds_api_results:
            logger.info(f'Odds API: {len(odds_api_results)} bookmakers for {home_team} vs {away_team}')
    except Exception as e:
        logger.warning(f'Odds API fetch failed: {e}')

    # 2. 竞彩官方赔率
    sporttery = _get_sporttery_odds(match_id, home_team, away_team)
    if sporttery:
        ho, do, ao = sporttery
        pred = _odds_to_prediction(ho, do, ao, '竞彩官方', '体彩官方赔率')
        if pred: results.append(pred)

    # 3. DB中的已有赔率
    try:
        from app.db_helper import db_cursor
        with db_cursor() as cur:
            if match_id:
                cur.execute('SELECT bookmaker, home_odds, draw_odds, away_odds FROM odds WHERE match_id=%s', (match_id,))
            for bm, ho, do, ao in cur.fetchall():
                if ho and do and ao and bm != 'sporttery_cn':
                    bm_names = {'william_hill': '威廉希尔', 'ladbrokes': '立博', 'bet365': 'Bet365',
                               'betfair': '必发交易所', 'pinnacle': '平博', 'crown': '皇冠', 'macau': '澳门彩票'}
                    name = bm_names.get(bm, bm)
                    pred = _odds_to_prediction(float(ho), float(do), float(ao), name, '博彩赔率')
                    if pred: results.append(pred)
    except Exception as e:
        logger.debug(f"DB odds fetch failed: {e}")

    # 去重
    seen = set()
    unique = []
    for r in results:
        if r['platform'] not in seen:
            seen.add(r['platform'])
            unique.append(r)
    return unique


def get_real_external_predictions(home_team, away_team):
    """从国际预测网站获取真实预测（优先用缓存，避免重复请求）"""
    results = []

    # 1. Forebet（使用全局缓存，不会每次重新请求）
    try:
        forebet = _fetch_forebet()  # 内部有30分钟缓存
        if forebet:
            for f in forebet:
                if _match_teams(home_team, away_team, f['home'], f['away']):
                    results.append({
                        'platform': 'Forebet',
                        'prediction': f['prediction'],
                        'confidence': 55,
                        'style': 'AI数学模型预测 + 历史数据',
                        'reasons': ['基于海量历史数据的大数据建模', '综合考虑近期状态和交锋记录'],
                        'data_source': 'real',
                    })
                    break  # 匹配到一场就够了
    except: pass

    # 2. BetExplorer
    try:
        be_data = _fetch_betexplorer()
        for be in be_data:
            if _match_teams(home_team, away_team, be['home'], be['away']):
                odds = be['odds']
                total = 1/odds['home'] + 1/odds['draw'] + 1/odds['away']
                hp = round(1/odds['home']/total*100, 1)
                dp = round(1/odds['draw']/total*100, 1)
                ap = round(1/odds['away']/total*100, 1)
                best = max([('home', hp), ('draw', dp), ('away', ap)], key=lambda x: x[1])
                results.append({
                    'platform': 'BetExplorer',
                    'prediction': best[0],
                    'confidence': min(70, best[1]+5),
                    'style': '多博彩公司赔率综合',
                    'reasons': [f'{best[0]}方向赔率最低，市场共识'],
                    'data_source': 'real',
                })
    except: pass

    # 3. 本地缓存的外部预测（之前成功抓取的）
    try:
        cache_file = os.path.join(DATA_DIR, 'external_predictions_cache.json')
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            for p in cached:
                if _match_teams(home_team, away_team, p.get('home', ''), p.get('away', '')):
                    results.append({
                        'platform': p.get('source', 'External'),
                        'prediction': p.get('prediction', 'home'),
                        'confidence': p.get('confidence', 50),
                        'style': p.get('style', '外部预测'),
                        'reasons': [p.get('reason', '')],
                        'data_source': 'external',
                    })
    except: pass

    # 去重
    seen = set()
    unique = []
    for r in results:
        if r['platform'] not in seen:
            seen.add(r['platform'])
            unique.append(r)
    return unique


def _get_sporttery_odds(match_id, home_team, away_team):
    """从体彩API获取标准盘赔率"""
    try:
        api = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c'
        resp = _smart_fetch(api, headers={'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/'}, timeout=10)
        if not resp:
            return None
        data = json.loads(resp)
        for info in data.get('value', {}).get('matchInfoList', []):
            for m in info.get('subMatchList', []):
                if m.get('homeTeamAllName') == home_team and m.get('awayTeamAllName') == away_team:
                    for pool in m.get('oddsList', []):
                        if pool.get('poolCode') == 'HAD':
                            return (float(pool['h']), float(pool['d']), float(pool['a']))
    except:
        pass
    return None


def _odds_to_prediction(ho, do, ao, platform_name, style):
    """将赔率转换为预测结果"""
    if not all([ho, do, ao]):
        return None
    total = 1/ho + 1/do + 1/ao
    hp = round(1/ho / total * 100, 1)
    dp = round(1/do / total * 100, 1)
    ap = round(1/ao / total * 100, 1)
    best = max([('home', hp), ('draw', dp), ('away', ap)], key=lambda x: x[1])
    conf = min(75, max(30, best[1] + 5))

    reasons = []
    if ho < 2.0: reasons.append(f'{platform_name}: 主胜低赔({ho})，市场看好主队')
    if do < 3.5: reasons.append(f'{platform_name}: 平赔偏低({do})，注意平局')
    if ao < 2.5: reasons.append(f'{platform_name}: 客胜赔付合理')
    if abs(ho - ao) < 0.3: reasons.append(f'{platform_name}: 赔率接近，实力均衡')
    if not reasons: reasons.append(f'{platform_name}: 赔率结构无明确倾向')

    return {
        'platform': platform_name, 'prediction': best[0],
        'confidence': conf, 'style': style,
        'reasons': reasons,
        'odds': {'home': ho, 'draw': do, 'away': ao},
        'data_source': 'real',
    }


# ═══════════════════════════════════════════════
#  定期抓取任务
# ═══════════════════════════════════════════════

def run_periodic_fetch():
    """定期抓取外部数据并缓存"""
    logger.info('Periodic data fetch...')
    try:
        forebet = _fetch_forebet()
        betexplorer = _fetch_betexplorer()
        flashscore = _fetch_flashscore()

        all_external = []
        for f in (forebet or []):
            all_external.append({'home': f['home'], 'away': f['away'], 'prediction': f['prediction'],
                                'source': 'Forebet', 'style': 'AI数学模型', 'confidence': 55,
                                'reason': '大数据建模预测'})
        for be in (betexplorer or []):
            odds = be['odds']; total = 1/odds['home']+1/odds['draw']+1/odds['away']
            hp = round(1/odds['home']/total*100); dp = round(1/odds['draw']/total*100); ap = round(1/odds['away']/total*100)
            best = max([('home',hp),('draw',dp),('away',ap)], key=lambda x:x[1])
            all_external.append({'home': be['home'], 'away': be['away'], 'prediction': best,
                                'source': 'BetExplorer', 'style': '多赔率综合', 'confidence': 50,
                                'reason': f'赔率对比分析 ({hp}/{dp}/{ap})'})

        if all_external:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, 'external_predictions_cache.json'), 'w', encoding='utf-8') as f:
                json.dump(all_external, f, ensure_ascii=False, indent=2)
            logger.info(f'Cached {len(all_external)} predictions')
    except Exception as e:
        logger.warning(f'Periodic fetch failed: {e}')


def load_player_values():
    """加载球员身价缓存"""
    cache_file = os.path.join(DATA_DIR, 'player_values.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}
