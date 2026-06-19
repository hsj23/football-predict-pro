"""外部预测聚合器 - 整合多个预测网站数据"""
import json, os, re, logging
from datetime import datetime

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')

# 已抓取的数据源
SOURCES = [
    # 国际AI预测
    'nerdytips', 'xgscore', 'tipsbet', 'soccervista', 'footballpredictions',
    # 国内预测
    'yucejia', 'zqcf', 'leisu', 'dongqiudi', 'okooo', '7m',
    # 社区/专家
    'bettingexpert', 'tipstrr', 'olbg',
]


# 全局缓存
_cache = None
_cache_time = 0


def load_all_external_predictions():
    """加载所有外部预测数据（带缓存）"""
    global _cache, _cache_time
    import time
    if _cache is not None and time.time() - _cache_time < 3600:
        return _cache

    all_preds = []

    for src in SOURCES:
        # Try JSON first
        json_file = os.path.join(DATA_DIR, f'{src}_predictions.json')
        html_file = os.path.join(DATA_DIR, f'{src}.html')

        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    logger.info(f'{src}: {len(data)} predictions from JSON')
                    all_preds.extend([{**p, 'source': src} for p in data])
                    continue
            except:
                pass

        # Try HTML
        if os.path.exists(html_file):
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    html = f.read()
                parsed = _parse_html_predictions(html, src)
                if parsed:
                    logger.info(f'{src}: {len(parsed)} predictions from HTML')
                    all_preds.extend([{**p, 'source': src} for p in parsed])
            except:
                pass

    # Deduplicate
    seen = set()
    unique = []
    for p in all_preds:
        key = f'{p.get("home","")}_{p.get("away","")}'
        if key.strip('_') and key not in seen:
            seen.add(key)
            unique.append(p)

    import time
    _cache = unique
    _cache_time = time.time()
    logger.info(f'External predictions: {len(unique)} from {len(SOURCES)} sources (cached)')
    return unique


def _parse_html_predictions(html, source):
    """通用HTML解析"""
    import re
    results = []

    # Find match patterns: team1 vs team2 with prediction
    # Pattern 1: Table rows with team names
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for tr in trs:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        texts = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
        texts = [re.sub(r'\s+', ' ', t).strip() for t in texts if t.strip()]

        if len(texts) < 3:
            continue

        home = away = prediction = ''
        for t in texts:
            t = t.strip()
            if 'VS' in t or 'vs' in t:
                parts = re.split(r'\s*(?:VS|vs)\s*', t)
                if len(parts) == 2:
                    home = re.sub(r'\([-+]\d+\)', '', parts[0]).strip()
                    away = re.sub(r'\([-+]\d+\)', '', parts[1]).strip()
            elif t in ['主胜', '胜', 'home', 'Home', '1']:
                prediction = 'home'
            elif t in ['平局', '平', 'draw', 'Draw', 'X', 'x']:
                prediction = 'draw'
            elif t in ['客胜', '负', 'away', 'Away', '2']:
                prediction = 'away'

        # If no VS found, try to extract teams from cells
        if not home:
            team_cells = [t for t in texts if 2 <= len(t) <= 30 and not re.match(r'^[\d\s\.\-:]+$', t)]
            if len(team_cells) >= 2:
                home = team_cells[0]
                away = team_cells[1]

        if home and away:
            results.append({'home': home, 'away': away, 'prediction': prediction or 'home'})

    # Pattern 2: Look for JSON-LD or embedded data
    if not results:
        jsons = re.findall(r'\{[^}]{30,300}\}', html)
        for j in jsons:
            if 'team' in j.lower() or 'prediction' in j.lower():
                try:
                    d = json.loads(j)
                    if 'homeTeam' in d and 'awayTeam' in d:
                        results.append({
                            'home': d.get('homeTeam', ''),
                            'away': d.get('awayTeam', ''),
                            'prediction': d.get('prediction', 'home')
                        })
                except:
                    pass

    return results[:500]  # Limit per source


# 中英文队名对照
TEAM_NAME_MAP = {
    '皇家马德里': 'real madrid', '巴塞罗那': 'barcelona', '马德里竞技': 'atletico madrid',
    '塞维利亚': 'sevilla', '拜仁慕尼黑': 'bayern munich', '多特蒙德': 'borussia dortmund',
    '勒沃库森': 'bayer leverkusen', '莱比锡': 'rb leipzig', '斯图加特': 'stuttgart',
    '曼城': 'manchester city', '利物浦': 'liverpool', '阿森纳': 'arsenal',
    '切尔西': 'chelsea', '曼联': 'manchester united', '热刺': 'tottenham',
    '纽卡斯尔': 'newcastle', '阿斯顿维拉': 'aston villa', '西汉姆': 'west ham',
    '国际米兰': 'inter milan', 'ac米兰': 'ac milan', '尤文图斯': 'juventus',
    '那不勒斯': 'napoli', '罗马': 'roma', '拉齐奥': 'lazio', '亚特兰大': 'atalanta',
    '巴黎圣日耳曼': 'paris saint germain', '马赛': 'marseille', '摩纳哥': 'monaco',
    '里昂': 'lyon', '里尔': 'lille', '雷恩': 'rennes', '朗斯': 'lens',
    '波尔图': 'porto', '本菲卡': 'benfica', '阿贾克斯': 'ajax', '埃因霍温': 'psv',
    '马尔默': 'malmo', '赫根': 'hacken', '哈马比': 'hammarby',
    '莫尔德': 'molde', '博德闪耀': 'bodo/glimt', '罗森博格': 'rosenborg',
    '赫尔辛基': 'helsinki', '库普斯': 'kups', '塞纳乔琪': 'sepn', '国际图尔': 'inter turku',
    '神户胜利船': 'kobe', '鹿岛鹿角': 'kashima', '浦和红钻': 'urawa',
    '横滨水手': 'yokohama', '大阪钢巴': 'gamba', '东京绿茵': 'tokyo verdy',
    '清水鼓动': 'shimizu', '冈山绿雉': 'okayama',
    '弗拉门戈': 'flamengo', '帕尔梅拉斯': 'palmeiras', '河床': 'river plate',
    '博卡青年': 'boca juniors',
}

def _translate_team(cn_name):
    """中文队名→英文"""
    return TEAM_NAME_MAP.get(cn_name, cn_name.lower().replace(' ', ''))


def get_consensus_prediction(home, away):
    """获取多源共识预测"""
    all_preds = load_all_external_predictions()
    matches = []

    home_en = _translate_team(home)
    away_en = _translate_team(away)

    for p in all_preds:
        ph = p.get('home', '').lower().strip()
        pa = p.get('away', '').lower().strip()

        # 中英文双向匹配
        h_match = (home in ph or ph in home or home_en in ph or ph in home_en)
        a_match = (away in pa or pa in away or away_en in pa or pa in away_en)

        if h_match and a_match:
            matches.append(p)

    if not matches:
        return None

    # 统计各预测的比例
    home_count = sum(1 for m in matches if m.get('prediction') == 'home')
    draw_count = sum(1 for m in matches if m.get('prediction') == 'draw')
    away_count = sum(1 for m in matches if m.get('prediction') == 'away')
    total = len(matches)

    consensus = max([('home', home_count), ('draw', draw_count), ('away', away_count)], key=lambda x: x[1])
    confidence = round(consensus[1] / total * 100) if total > 0 else 50

    return {
        'prediction': consensus[0],
        'confidence': confidence,
        'total_sources': total,
        'home_votes': home_count,
        'draw_votes': draw_count,
        'away_votes': away_count,
    }
