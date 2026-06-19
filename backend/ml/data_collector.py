"""
历史数据采集器 - 从多个网络数据源批量获取历史比赛数据（含比分和赔率）
数据来源:
  1. OpenLigaDB API - 德甲/德乙/英超/西甲/意甲/法甲 多个赛季
  2. TheSportsDB - 全球足球数据（免费）
输出: training_data.json (统一格式的训练数据)
"""
import json
import os
import time
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'training_data.json')

# OpenLigaDB 支持的联赛及赛季
# 每个联赛代码 + 赛季年份
LEAGUE_SEASONS = {
    'bl1': [2024, 2023, 2022, 2021],      # 德甲
    'bl2': [2024, 2023, 2022],             # 德乙
    'pl1': [2024, 2023],                   # 英超 (可能有限)
    'laliga1': [2024, 2023],               # 西甲
    'sa1': [2024, 2023],                   # 意甲
    'fl1': [2024, 2023],                   # 法甲
    'cl': [2024, 2023],                    # 欧冠
}

# OpenLigaDB 联赛名称
LEAGUE_NAMES = {
    'bl1': '德甲', 'bl2': '德乙',
    'pl1': '英超', 'laliga1': '西甲',
    'sa1': '意甲', 'fl1': '法甲',
    'cl': '欧冠', 'el': '欧联杯',
}

# 球队名称 英→中 映射（关键球队）
TEAM_CN = {
    # 德甲
    'Bayern München': '拜仁慕尼黑', 'FC Bayern München': '拜仁慕尼黑',
    'Borussia Dortmund': '多特蒙德',
    'RB Leipzig': '莱比锡', 'RasenBallsport Leipzig': '莱比锡',
    'Bayer 04 Leverkusen': '勒沃库森', 'Bayer Leverkusen': '勒沃库森',
    'Eintracht Frankfurt': '法兰克福',
    'VfB Stuttgart': '斯图加特',
    'VfL Wolfsburg': '沃尔夫斯堡',
    'Borussia Mönchengladbach': '门兴格拉德巴赫',
    'SC Freiburg': '弗赖堡',
    'TSG 1899 Hoffenheim': '霍芬海姆', 'TSG Hoffenheim': '霍芬海姆',
    '1. FC Union Berlin': '柏林联合', 'FC Union Berlin': '柏林联合',
    'FC Augsburg': '奥格斯堡',
    '1. FSV Mainz 05': '美因茨', 'FSV Mainz 05': '美因茨',
    'SV Werder Bremen': '云达不莱梅', 'Werder Bremen': '云达不莱梅',
    'VfL Bochum 1848': '波鸿', 'VfL Bochum': '波鸿',
    '1. FC Heidenheim 1846': '海登海姆', '1. FC Heidenheim': '海登海姆',
    '1. FC Köln': '科隆', 'FC Köln': '科隆',
    'SV Darmstadt 98': '达姆施塔特',
    'FC Schalke 04': '沙尔克04', 'Schalke 04': '沙尔克',
    'Hertha BSC': '柏林赫塔',
    'Hamburger SV': '汉堡',
    'FC St. Pauli': '圣保利',
    'Holstein Kiel': '基尔',
    '1. FC Nürnberg': '纽伦堡',
    'Fortuna Düsseldorf': '杜塞尔多夫',
    'Hannover 96': '汉诺威96',
    'Karlsruher SC': '卡尔斯鲁厄',
    'SC Paderborn 07': '帕德博恩',
    'SpVgg Greuther Fürth': '菲尔特',
    '1. FC Kaiserslautern': '凯泽斯劳滕',
    '1. FC Magdeburg': '马格德堡',
    'Eintracht Braunschweig': '不伦瑞克',
    'SSV Jahn Regensburg': '雷根斯堡',
    'SV 07 Elversberg': '埃尔弗斯贝格',
    'Preußen Münster': '普鲁士明斯特',
    'SSV Ulm 1846': '乌尔姆',
    'DSC Arminia Bielefeld': '比勒费尔德',
    # 英超
    'Manchester City': '曼城', 'Manchester City FC': '曼城',
    'Manchester United': '曼联', 'Manchester United FC': '曼联',
    'Liverpool FC': '利物浦', 'FC Liverpool': '利物浦',
    'Chelsea FC': '切尔西', 'Chelsea': '切尔西',
    'Arsenal FC': '阿森纳', 'FC Arsenal': '阿森纳',
    'Tottenham Hotspur': '热刺', 'Tottenham Hotspur FC': '热刺',
    'Newcastle United': '纽卡斯尔', 'Newcastle United FC': '纽卡斯尔',
    'Aston Villa': '阿斯顿维拉', 'Aston Villa FC': '阿斯顿维拉',
    'Brighton & Hove Albion': '布莱顿', 'Brighton & Hove Albion FC': '布莱顿',
    'West Ham United': '西汉姆', 'West Ham United FC': '西汉姆',
    'Wolverhampton Wanderers': '狼队', 'Wolverhampton Wanderers FC': '狼队',
    'Everton FC': '埃弗顿', 'Everton': '埃弗顿',
    'Brentford FC': '布伦特福德', 'Brentford': '布伦特福德',
    'Fulham FC': '富勒姆', 'Fulham': '富勒姆',
    'Crystal Palace': '水晶宫', 'Crystal Palace FC': '水晶宫',
    'Nottingham Forest': '诺丁汉森林',
    'AFC Bournemouth': '伯恩茅斯', 'Bournemouth': '伯恩茅斯',
    'Leicester City': '莱斯特城',
    'Southampton FC': '南安普顿',
    # 西甲
    'Real Madrid': '皇家马德里',
    'FC Barcelona': '巴塞罗那', 'Barcelona': '巴塞罗那',
    'Atlético Madrid': '马德里竞技', 'Atletico Madrid': '马德里竞技',
    'Sevilla FC': '塞维利亚', 'Sevilla': '塞维利亚',
    'Valencia CF': '瓦伦西亚',
    'Villarreal CF': '比利亚雷亚尔',
    'Real Sociedad': '皇家社会',
    'Real Betis': '贝蒂斯', 'Real Betis Balompié': '贝蒂斯',
    'Athletic Club': '毕尔巴鄂竞技', 'Athletic Bilbao': '毕尔巴鄂竞技',
    'Getafe CF': '赫塔费',
    'CA Osasuna': '奥萨苏纳',
    'RC Celta': '塞尔塔', 'RC Celta de Vigo': '塞尔塔',
    'RCD Mallorca': '马洛卡',
    'Rayo Vallecano': '巴列卡诺',
    'Girona FC': '赫罗纳',
    'Granada CF': '格拉纳达',
    'UD Almería': '阿尔梅里亚',
    'Cádiz CF': '加的斯',
    'UD Las Palmas': '拉斯帕尔马斯',
    'Deportivo Alavés': '阿拉维斯',
    # 意甲
    'Juventus FC': '尤文图斯', 'Juventus Turin': '尤文图斯',
    'AC Milan': 'AC米兰',
    'Inter Milan': '国际米兰', 'FC Internazionale': '国际米兰',
    'SSC Napoli': '那不勒斯',
    'AS Roma': '罗马',
    'SS Lazio': '拉齐奥',
    'Atalanta BC': '亚特兰大', 'Atalanta Bergamasca Calcio': '亚特兰大',
    'ACF Fiorentina': '佛罗伦萨',
    'Bologna FC': '博洛尼亚',
    'Torino FC': '都灵',
    'Udinese Calcio': '乌迪内斯',
    'US Sassuolo': '萨索洛',
    'Empoli FC': '恩波利',
    'AC Monza': '蒙扎',
    'Hellas Verona': '维罗纳',
    'US Lecce': '莱切',
    'Cagliari Calcio': '卡利亚里',
    'Genoa CFC': '热那亚',
    'Parma Calcio': '帕尔马',
    'Venezia FC': '威尼斯',
    # 法甲
    'Paris Saint-Germain': '巴黎圣日耳曼', 'Paris Saint-Germain FC': '巴黎圣日耳曼',
    'Olympique Marseille': '马赛',
    'Olympique Lyon': '里昂', 'Olympique Lyonnais': '里昂',
    'AS Monaco': '摩纳哥', 'AS Monaco FC': '摩纳哥',
    'LOSC Lille': '里尔',
    'OGC Nice': '尼斯',
    'RC Lens': '朗斯',
    'Stade Rennais FC': '雷恩', 'Stade Rennais': '雷恩',
    'RC Strasbourg': '斯特拉斯堡',
    'FC Nantes': '南特',
    'Montpellier HSC': '蒙彼利埃',
    'Toulouse FC': '图卢兹',
    'Stade Brestois 29': '布雷斯特',
    'Stade de Reims': '兰斯',
    'Le Havre AC': '勒阿弗尔',
    'FC Lorient': '洛里昂',
    'FC Metz': '梅斯',
    'Clermont Foot 63': '克莱蒙',
    'AJ Auxerre': '欧塞尔',
    'Angers SCO': '昂热',
}


def translate_team(name_en: str) -> str:
    """翻译英文队名为中文，未知的保持英文"""
    if name_en in TEAM_CN:
        return TEAM_CN[name_en]
    # 尝试模糊匹配
    for en, cn in TEAM_CN.items():
        if name_en.lower() in en.lower() or en.lower() in name_en.lower():
            return cn
    return name_en


def fetch_openligadb_season(league_code: str, season_year: int) -> List[Dict]:
    """从OpenLigaDB获取一个赛季的比赛数据"""
    url = f"https://api.openligadb.de/getmatchdata/{league_code}/{season_year}"
    league_name = LEAGUE_NAMES.get(league_code, league_code)

    try:
        resp = requests.get(url, timeout=30,
                          headers={'User-Agent': 'FootballDataCollector/1.0'})
        if resp.status_code != 200:
            logger.warning(f"  {league_name} {season_year}: HTTP {resp.status_code}")
            return []

        data = resp.json()
        if not data:
            return []

        matches = []
        for item in data:
            try:
                if not item.get('matchIsFinished'):
                    continue

                results = item.get('matchResults', [])
                if not results:
                    continue

                latest = results[-1]
                home_score = latest.get('pointsTeam1', 0)
                away_score = latest.get('pointsTeam2', 0)

                home_en = item.get('team1', {}).get('teamName', '')
                away_en = item.get('team2', {}).get('teamName', '')

                home_cn = translate_team(home_en)
                away_cn = translate_team(away_en)

                # 从最终比分获取结果
                full_score = f"{home_score}:{away_score}"

                # OpenLigaDB 不直接提供赔率，但从最终比分我们知道结果
                matches.append({
                    'home': home_cn,
                    'away': away_cn,
                    'home_en': home_en,
                    'away_en': away_en,
                    'league': league_name,
                    'full_score': full_score,
                    'home_score': home_score,
                    'away_score': away_score,
                    'date': item.get('matchDateTime', '')[:10],
                    'source': f'openligadb_{league_code}_{season_year}',
                    # 没有赔率数据，标记为无赔率
                    'odds': None,
                })
            except Exception:
                continue

        return matches

    except requests.Timeout:
        logger.warning(f"  {league_name} {season_year}: 请求超时")
        return []
    except Exception as e:
        logger.warning(f"  {league_name} {season_year}: {e}")
        return []


def generate_odds_from_result(full_score: str) -> Optional[List[float]]:
    """
    根据实际结果反推合理赔率范围（用于训练特征中的赔率估算）
    这不如真实赔率准确，但比完全随机好
    """
    try:
        parts = full_score.split(':')
        home_goals = int(parts[0])
        away_goals = int(parts[1])
    except (ValueError, IndexError):
        return None

    # 根据比分估算赔率
    goal_diff = home_goals - away_goals

    if goal_diff >= 3:
        # 主队大胜 → 主队低赔
        return [1.30, 4.50, 8.00]
    elif goal_diff == 2:
        return [1.55, 3.80, 5.50]
    elif goal_diff == 1:
        return [1.85, 3.40, 4.00]
    elif goal_diff == 0:
        if home_goals == 0:
            return [2.30, 2.90, 3.20]  # 0-0 平局
        else:
            return [2.50, 3.30, 2.70]  # 高比分平局
    elif goal_diff == -1:
        return [4.00, 3.40, 1.85]
    elif goal_diff == -2:
        return [5.50, 3.80, 1.55]
    else:
        return [8.00, 4.50, 1.30]


def collect_all_data():
    """收集所有可获取的历史数据"""
    all_matches = []

    logger.info("=" * 60)
    logger.info("开始收集历史比赛数据...")
    logger.info("=" * 60)

    # 1. 从 OpenLigaDB 获取多赛季数据
    for league_code, seasons in LEAGUE_SEASONS.items():
        league_name = LEAGUE_NAMES.get(league_code, league_code)
        for season_year in seasons:
            logger.info(f"获取 {league_name} {season_year}/{season_year+1} 赛季...")
            matches = fetch_openligadb_season(league_code, season_year)
            if matches:
                logger.info(f"  → {len(matches)} 场比赛")
                all_matches.extend(matches)
            time.sleep(0.3)  # 请求间隔

    # 2. 加载已有的 jczq_results.json (有真实赔率数据)
    jczq_file = os.path.join(DATA_DIR, 'jczq_results.json')
    if os.path.exists(jczq_file):
        with open(jczq_file, 'r', encoding='utf-8') as f:
            jczq_data = json.load(f)
        if isinstance(jczq_data, list):
            logger.info(f"加载竞彩结果: {len(jczq_data)} 条")
            for m in jczq_data:
                if m.get('full_score') and ':' in str(m.get('full_score', '')):
                    m['source'] = 'jczq_results'
                    all_matches.append(m)

    # 去重
    seen = set()
    unique = []
    for m in all_matches:
        home = m.get('home', '')
        away = m.get('away', '')
        date = m.get('date', '')
        key = f"{home}_{away}_{date}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.info(f"\n总计: {len(unique)} 场唯一比赛 (原始 {len(all_matches)})")

    # 统计各联赛数据量
    league_counts = {}
    for m in unique:
        league = m.get('league', 'unknown')
        league_counts[league] = league_counts.get(league, 0) + 1

    logger.info("各联赛数据分布:")
    for league, count in sorted(league_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {league}: {count} 场")

    # 统计赔率情况（不生成假赔率，避免数据泄露）
    # 没有真实赔率的比赛，特征工程会自动基于球队实力估算赔率
    with_odds = 0
    without_odds = 0
    for m in unique:
        if m.get('odds') and len(m['odds']) == 3:
            with_odds += 1
        # 不生成假赔率！让特征工程自己处理缺失赔率

    logger.info(f"有真实赔率: {with_odds} 场, 估算赔率: {without_odds} 场")

    # 保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    logger.info(f"\n训练数据已保存: {OUTPUT_FILE}")
    logger.info(f"共 {len(unique)} 场比赛")

    return unique


if __name__ == "__main__":
    collect_all_data()
