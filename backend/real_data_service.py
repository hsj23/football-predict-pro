"""
真实足球数据服务 - 核心数据层
数据来源:
  1. OpenLigaDB API (免费, 无需API Key) - 德甲/英超/西甲/意甲/法甲/欧冠
  2. TheSportsDB (免费) - 全球足球数据
  3. football-data.org (免费层) - 欧洲主流联赛
所有数据均为真实API返回, 绝不生成随机假数据
"""
import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class RealDataService:
    """真实足球数据服务 - 统一数据入口"""

    # OpenLigaDB 联赛代码
    OPENLIGADB_LEAGUES = {
        'bl1': '德甲', 'bl2': '德乙',
        'pl1': '英超', 'laliga1': '西甲',
        'sa1': '意甲', 'fl1': '法甲',
        'cl': '欧冠', 'el': '欧联杯',
    }

    # 球队名称中英对照（来自 OpenLigaDB 官方名称）
    TEAM_NAME_MAP = {
        # 英超
        'Manchester City': '曼城', 'Manchester City FC': '曼城',
        'Manchester United': '曼联', 'Manchester United FC': '曼联',
        'Liverpool': '利物浦', 'FC Liverpool': '利物浦', 'Liverpool FC': '利物浦',
        'Chelsea': '切尔西', 'Chelsea FC': '切尔西',
        'Arsenal': '阿森纳', 'FC Arsenal': '阿森纳', 'Arsenal FC': '阿森纳',
        'Tottenham': '热刺', 'Tottenham Hotspur': '热刺', 'Tottenham Hotspur FC': '热刺',
        'Newcastle': '纽卡斯尔', 'Newcastle United': '纽卡斯尔', 'Newcastle United FC': '纽卡斯尔',
        'Aston Villa': '阿斯顿维拉', 'Aston Villa FC': '阿斯顿维拉',
        'Brighton': '布莱顿', 'Brighton & Hove Albion': '布莱顿', 'Brighton & Hove Albion FC': '布莱顿',
        'West Ham': '西汉姆', 'West Ham United': '西汉姆', 'West Ham United FC': '西汉姆',
        'Brentford': '布伦特福德', 'Brentford FC': '布伦特福德',
        'Fulham': '富勒姆', 'Fulham FC': '富勒姆',
        'Crystal Palace': '水晶宫', 'Crystal Palace FC': '水晶宫',
        'Wolverhampton': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolverhampton Wanderers FC': '狼队', 'Wolves': '狼队',
        'Everton': '埃弗顿', 'Everton FC': '埃弗顿',
        'Nottingham Forest': '诺丁汉森林', 'Nottingham': '诺丁汉森林',
        'Bournemouth': '伯恩茅斯', 'AFC Bournemouth': '伯恩茅斯',
        'Sheffield United': '谢菲尔德联',
        'Burnley': '伯恩利', 'Burnley FC': '伯恩利',
        'Luton Town': '卢顿', 'Luton': '卢顿',
        'Ipswich Town': '伊普斯维奇', 'Ipswich': '伊普斯维奇',
        'Leicester City': '莱斯特城', 'Leicester': '莱斯特城',
        'Southampton': '南安普顿',
        # 德甲
        'Bayern München': '拜仁慕尼黑', 'FC Bayern München': '拜仁慕尼黑', 'Bayern Munich': '拜仁慕尼黑',
        'Borussia Dortmund': '多特蒙德', 'Dortmund': '多特蒙德',
        'RB Leipzig': '莱比锡', 'RasenBallsport Leipzig': '莱比锡',
        'Leverkusen': '勒沃库森', 'Bayer 04 Leverkusen': '勒沃库森', 'Bayer Leverkusen': '勒沃库森',
        'Eintracht Frankfurt': '法兰克福', 'Frankfurt': '法兰克福',
        'VfB Stuttgart': '斯图加特', 'Stuttgart': '斯图加特',
        'VfL Wolfsburg': '沃尔夫斯堡', 'Wolfsburg': '沃尔夫斯堡',
        'Borussia Mönchengladbach': '门兴格拉德巴赫', 'Gladbach': '门兴格拉德巴赫',
        'SC Freiburg': '弗赖堡', 'Freiburg': '弗赖堡',
        'TSG Hoffenheim': '霍芬海姆', 'Hoffenheim': '霍芬海姆',
        '1. FC Union Berlin': '柏林联合', 'Union Berlin': '柏林联合',
        'FC Augsburg': '奥格斯堡', 'Augsburg': '奥格斯堡',
        '1. FSV Mainz 05': '美因茨', 'Mainz 05': '美因茨', 'Mainz': '美因茨',
        'SV Werder Bremen': '云达不莱梅', 'Werder Bremen': '云达不莱梅', 'Bremen': '云达不莱梅',
        'VfL Bochum': '波鸿', 'Bochum': '波鸿',
        'FC St. Pauli': '圣保利', 'St. Pauli': '圣保利',
        '1. FC Heidenheim': '海登海姆', 'Heidenheim': '海登海姆',
        '1. FC Köln': '科隆', 'Köln': '科隆', 'FC Köln': '科隆',
        'Hamburger SV': '汉堡', 'Hamburg': '汉堡',
        'Darmstadt 98': '达姆施塔特', 'Darmstadt': '达姆施塔特',
        # 西甲
        'Real Madrid': '皇家马德里',
        'Barcelona': '巴塞罗那', 'FC Barcelona': '巴塞罗那',
        'Atletico Madrid': '马德里竞技', 'Atlético Madrid': '马德里竞技',
        'Sevilla': '塞维利亚', 'Sevilla FC': '塞维利亚',
        'Valencia': '瓦伦西亚', 'FC Valencia': '瓦伦西亚', 'Valencia CF': '瓦伦西亚',
        'Villarreal': '比利亚雷亚尔', 'Villarreal CF': '比利亚雷亚尔',
        'Real Sociedad': '皇家社会',
        'Real Betis': '贝蒂斯', 'Betis': '贝蒂斯',
        'Athletic Club': '毕尔巴鄂竞技', 'Athletic Bilbao': '毕尔巴鄂竞技',
        'Getafe': '赫塔费', 'Getafe CF': '赫塔费',
        'Osasuna': '奥萨苏纳', 'CA Osasuna': '奥萨苏纳',
        'Celta Vigo': '塞尔塔', 'Celta': '塞尔塔', 'RC Celta': '塞尔塔',
        'Mallorca': '马洛卡', 'RCD Mallorca': '马洛卡',
        'Rayo Vallecano': '巴列卡诺',
        'Girona': '赫罗纳', 'FC Girona': '赫罗纳',
        'Almeria': '阿尔梅里亚', 'UD Almería': '阿尔梅里亚',
        'Cádiz': '加的斯', 'Cádiz CF': '加的斯',
        'Granada': '格拉纳达', 'Granada CF': '格拉纳达',
        'Las Palmas': '拉斯帕尔马斯', 'UD Las Palmas': '拉斯帕尔马斯',
        'Alavés': '阿拉维斯', 'Deportivo Alavés': '阿拉维斯',
        # 意甲
        'Juventus': '尤文图斯', 'Juventus FC': '尤文图斯', 'Juventus Turin': '尤文图斯',
        'AC Milan': 'AC米兰', 'Milan': 'AC米兰',
        'Inter': '国际米兰', 'Inter Milan': '国际米兰', 'FC Internazionale': '国际米兰',
        'Napoli': '那不勒斯', 'SSC Napoli': '那不勒斯',
        'Roma': '罗马', 'AS Roma': '罗马',
        'Lazio': '拉齐奥', 'SS Lazio': '拉齐奥',
        'Atalanta': '亚特兰大', 'Atalanta BC': '亚特兰大', 'Atalanta Bergamo': '亚特兰大',
        'Fiorentina': '佛罗伦萨', 'ACF Fiorentina': '佛罗伦萨',
        'Bologna': '博洛尼亚', 'Bologna FC': '博洛尼亚',
        'Torino': '都灵', 'Torino FC': '都灵',
        'Udinese': '乌迪内斯', 'Udinese Calcio': '乌迪内斯',
        'Sassuolo': '萨索洛', 'US Sassuolo': '萨索洛',
        'Empoli': '恩波利', 'Empoli FC': '恩波利',
        'Monza': '蒙扎', 'AC Monza': '蒙扎',
        'Verona': '维罗纳', 'Hellas Verona': '维罗纳',
        'Lecce': '莱切', 'US Lecce': '莱切',
        'Cagliari': '卡利亚里', 'Cagliari Calcio': '卡利亚里',
        'Genoa': '热那亚', 'Genoa CFC': '热那亚',
        'Venezia': '威尼斯', 'Venezia FC': '威尼斯',
        'Parma': '帕尔马', 'Parma Calcio': '帕尔马',
        'Como': '科莫', 'Como 1907': '科莫',
        # 法甲
        'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼', 'Paris SG': '巴黎圣日耳曼',
        'Marseille': '马赛', 'Olympique Marseille': '马赛', 'OM': '马赛',
        'Lyon': '里昂', 'Olympique Lyon': '里昂', 'OL': '里昂',
        'Monaco': '摩纳哥', 'AS Monaco': '摩纳哥',
        'Lille': '里尔', 'LOSC Lille': '里尔', 'LOSC': '里尔',
        'Nice': '尼斯', 'OGC Nice': '尼斯',
        'Lens': '朗斯', 'RC Lens': '朗斯',
        'Rennes': '雷恩', 'Stade Rennais': '雷恩',
        'Strasbourg': '斯特拉斯堡', 'RC Strasbourg': '斯特拉斯堡',
        'Nantes': '南特', 'FC Nantes': '南特',
        'Montpellier': '蒙彼利埃', 'Montpellier HSC': '蒙彼利埃',
        'Toulouse': '图卢兹', 'Toulouse FC': '图卢兹',
        'Brest': '布雷斯特', 'Stade Brest': '布雷斯特',
        'Reims': '兰斯', 'Stade Reims': '兰斯',
        'Le Havre': '勒阿弗尔', 'FC Le Havre': '勒阿弗尔',
        'Metz': '梅斯', 'FC Metz': '梅斯',
        'Lorient': '洛里昂', 'FC Lorient': '洛里昂',
        'Clermont': '克莱蒙', 'Clermont Foot': '克莱蒙',
        'Saint-Étienne': '圣埃蒂安', 'AS Saint-Étienne': '圣埃蒂安',
        'Auxerre': '欧塞尔', 'AJ Auxerre': '欧塞尔',
        'Angers': '昂热', 'Angers SCO': '昂热',
        # 欧冠
        'Paris Saint Germain': '巴黎圣日耳曼',
        # 德乙
        'DSC Arminia Bielefeld': '比勒费尔德', 'Arminia Bielefeld': '比勒费尔德',
        'Hertha BSC': '柏林赫塔', 'Hertha BSC Berlin': '柏林赫塔',
        'SV 07 Elversberg': '埃尔弗斯贝格', 'SV Elversberg': '埃尔弗斯贝格',
        '1. FC Magdeburg': '马格德堡', 'FC Magdeburg': '马格德堡',
        '1. FC Kaiserslautern': '凯泽斯劳滕', 'Kaiserslautern': '凯泽斯劳滕',
        'Karlsruher SC': '卡尔斯鲁厄', 'Karlsruhe': '卡尔斯鲁厄',
        'Hannover 96': '汉诺威96', 'Hannover': '汉诺威',
        '1. FC Nürnberg': '纽伦堡', 'Nürnberg': '纽伦堡', 'FC Nürnberg': '纽伦堡',
        'Preußen Münster': '普鲁士明斯特', 'SC Preußen Münster': '普鲁士明斯特',
        'VfL Bochum': '波鸿', 'Bochum': '波鸿',
        'Fortuna Düsseldorf': '杜塞尔多夫', 'Düsseldorf': '杜塞尔多夫',
        'SSV Ulm 1846': '乌尔姆', 'SSV Ulm': '乌尔姆',
        'SSV Jahn Regensburg': '雷根斯堡', 'Jahn Regensburg': '雷根斯堡',
        'SC Paderborn 07': '帕德博恩', 'Paderborn': '帕德博恩',
        'SV Darmstadt 98': '达姆施塔特', 'Darmstadt': '达姆施塔特',
        'Eintracht Braunschweig': '不伦瑞克', 'Braunschweig': '不伦瑞克',
        'SpVgg Greuther Fürth': '菲尔特', 'Greuther Fürth': '菲尔特',
        'FC Schalke 04': '沙尔克04', 'Schalke 04': '沙尔克', 'Schalke': '沙尔克',
        'Holstein Kiel': '基尔', 'Kiel': '基尔',
        # 其他常见球队
        'RSC Anderlecht': '安德莱赫特',
        'FC Porto': '波尔图', 'Porto': '波尔图',
        'SL Benfica': '本菲卡', 'Benfica': '本菲卡',
        'Ajax Amsterdam': '阿贾克斯', 'Ajax': '阿贾克斯',
        'PSV Eindhoven': '埃因霍温', 'PSV': '埃因霍温',
        'Feyenoord Rotterdam': '费耶诺德', 'Feyenoord': '费耶诺德',
        'Celtic Glasgow': '凯尔特人', 'Celtic': '凯尔特人',
        'Galatasaray Istanbul': '加拉塔萨雷', 'Galatasaray': '加拉塔萨雷',
        'Olympiacos Piräus': '奥林匹亚科斯', 'Olympiacos': '奥林匹亚科斯',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FootballPredictPro/2.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json',
        })
        self._request_count = 0
        self._last_request_time = 0

    def _rate_limit(self):
        """API 请求频率限制 - 每秒最多5个请求"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1

    def _api_get(self, url: str, timeout: int = 15) -> Optional[dict]:
        """发送 API 请求"""
        self._rate_limit()
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                logger.debug(f"API 404: {url}")
            else:
                logger.warning(f"API 返回 {resp.status_code}: {url}")
        except requests.Timeout:
            logger.warning(f"API 请求超时: {url}")
        except requests.ConnectionError:
            logger.warning(f"API 连接失败: {url}")
        except Exception as e:
            logger.error(f"API 请求异常: {url} - {e}")
        return None

    # ── OpenLigaDB API ──────────────────────────────────────────

    def _translate_team(self, name: str) -> str:
        """翻译英文队名为中文"""
        return self.TEAM_NAME_MAP.get(name, name)

    def _parse_openligadb_match(self, item: dict, league_code: str) -> Optional[dict]:
        """解析单场 OpenLigaDB 比赛数据"""
        try:
            match_time_str = item.get('matchDateTime', '')
            if match_time_str:
                try:
                    match_dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                    # 转为北京时间显示
                    match_dt_beijing = match_dt + timedelta(hours=8)
                    match_time = match_dt_beijing.strftime('%Y-%m-%d %H:%M')
                except:
                    match_time = match_time_str
            else:
                match_time = '待定'

            home_en = item.get('team1', {}).get('teamName', '')
            away_en = item.get('team2', {}).get('teamName', '')
            home = self._translate_team(home_en)
            away = self._translate_team(away_en)

            league_name = self.OPENLIGADB_LEAGUES.get(league_code, '未知')

            # 比分
            results = item.get('matchResults', [])
            home_score = 0
            away_score = 0
            if results:
                latest = results[-1]
                home_score = latest.get('pointsTeam1', 0)
                away_score = latest.get('pointsTeam2', 0)

            is_finished = item.get('matchIsFinished', False)
            match_minute = item.get('matchMinute', 0)

            if is_finished:
                status = 'finished'
            elif match_minute > 0:
                status = 'live'
            else:
                status = 'scheduled'

            return {
                'match_id': f"OLD_{item.get('matchID', '')}",
                'league_code': league_code,
                'league_name': league_name,
                'home_team_name': home,
                'away_team_name': away,
                'home_team_name_en': home_en,
                'away_team_name_en': away_en,
                'match_time': match_time,
                'home_score': home_score,
                'away_score': away_score,
                'status': status,
                'minute': match_minute if status == 'live' else 0,
                'is_finished': is_finished,
                'source': 'openligadb',
            }
        except Exception as e:
            logger.debug(f"解析比赛数据异常: {e}")
            return None

    def get_openligadb_league_matches(self, league_code: str) -> List[dict]:
        """获取指定联赛当前赛季的全部比赛"""
        url = f"https://api.openligadb.de/getmatchdata/{league_code}"
        data = self._api_get(url)
        if not data:
            return []

        matches = []
        for item in data:
            m = self._parse_openligadb_match(item, league_code)
            if m:
                matches.append(m)

        logger.info(f"[{self.OPENLIGADB_LEAGUES.get(league_code, league_code)}] 获取 {len(matches)} 场比赛")
        return matches

    def get_all_openligadb_matches(self) -> List[dict]:
        """获取所有联赛的比赛"""
        all_matches = []
        for code in self.OPENLIGADB_LEAGUES:
            matches = self.get_openligadb_league_matches(code)
            all_matches.extend(matches)
        return all_matches

    def get_today_matches(self) -> List[dict]:
        """获取今天的比赛（所有数据源）"""
        today = datetime.now().strftime('%Y-%m-%d')
        matches = []

        # 主要来源: OpenLigaDB
        for code in self.OPENLIGADB_LEAGUES:
            url = f"https://api.openligadb.de/getmatchdata/{code}"
            data = self._api_get(url)
            if not data:
                continue
            for item in data:
                match_time_str = item.get('matchDateTime', '')
                if today in match_time_str:
                    m = self._parse_openligadb_match(item, code)
                    if m:
                        matches.append(m)

        logger.info(f"今日比赛: {len(matches)} 场")
        return matches

    def get_upcoming_matches(self, days: int = 3) -> List[dict]:
        """获取未来N天的比赛"""
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        matches = []

        for code in self.OPENLIGADB_LEAGUES:
            url = f"https://api.openligadb.de/getmatchdata/{code}"
            data = self._api_get(url)
            if not data:
                continue
            for item in data:
                m = self._parse_openligadb_match(item, code)
                if not m:
                    continue
                try:
                    match_dt = datetime.strptime(m['match_time'], '%Y-%m-%d %H:%M')
                    if now <= match_dt <= cutoff:
                        matches.append(m)
                except:
                    continue

        return matches

    # ── 球队近期战绩（基于 OpenLigaDB 真实数据） ─────────────────

    def get_team_recent_form(self, team_name: str, league_code: str = 'bl1') -> dict:
        """获取球队近期战绩 - 基于真实历史比赛"""
        url = f"https://api.openligadb.de/getmatchdata/{league_code}"
        data = self._api_get(url)
        if not data:
            return self._empty_form(team_name)

        # 找出该球队的近5场已结束比赛
        team_matches = []
        for item in data:
            if not item.get('matchIsFinished'):
                continue
            home = item.get('team1', {}).get('teamName', '')
            away = item.get('team2', {}).get('teamName', '')
            if team_name not in (home, away) and self._translate_team(home) != team_name and self._translate_team(away) != team_name:
                continue

            results = item.get('matchResults', [])
            if not results:
                continue
            latest = results[-1]
            home_score = latest.get('pointsTeam1', 0)
            away_score = latest.get('pointsTeam2', 0)

            is_home = (home == team_name or self._translate_team(home) == team_name)
            if is_home:
                gs, ga = home_score, away_score
            else:
                gs, ga = away_score, home_score

            if gs > ga:
                result = 'W'
            elif gs == ga:
                result = 'D'
            else:
                result = 'L'

            match_time_str = item.get('matchDateTime', '')
            team_matches.append({
                'date': match_time_str[:10] if match_time_str else '',
                'result': result,
                'goals_scored': gs,
                'goals_against': ga,
                'opponent': self._translate_team(away if is_home else home),
            })

        # 按日期排序取最近5场
        team_matches.sort(key=lambda x: x['date'], reverse=True)
        recent = team_matches[:5]

        if not recent:
            return self._empty_form(team_name)

        results = [m['result'] for m in recent]
        wins = results.count('W')
        draws = results.count('D')
        losses = results.count('L')
        goals_for = sum(m['goals_scored'] for m in recent)
        goals_against = sum(m['goals_against'] for m in recent)

        return {
            'team_name': team_name,
            'recent_results': results,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'goals_for': goals_for,
            'goals_against': goals_against,
            'win_rate': round(wins / len(results) * 100, 1),
            'form_score': round((wins * 3 + draws) / (len(results) * 3) * 100, 1),
            'detail': recent,
            'source': 'openligadb_real',
        }

    @staticmethod
    def _empty_form(team_name: str) -> dict:
        return {
            'team_name': team_name,
            'recent_results': [],
            'wins': 0,
            'draws': 0,
            'losses': 0,
            'goals_for': 0,
            'goals_against': 0,
            'win_rate': 0,
            'form_score': 0,
            'detail': [],
            'source': 'no_data',
        }

    # ── TheSportsDB (备用免费API) ────────────────────────────────

    def get_sportsdb_today_matches(self) -> List[dict]:
        """从 TheSportsDB 获取今日足球比赛"""
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        url = f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={today}&s=Soccer"
        data = self._api_get(url)
        if not data:
            return []

        events = data.get('events') or []
        matches = []
        for event in events:
            home_score = event.get('intHomeScore')
            away_score = event.get('intAwayScore')
            matches.append({
                'match_id': f"TSDB_{event.get('idEvent', '')}",
                'league_name': event.get('strLeague', ''),
                'home_team_name': event.get('strHomeTeam', ''),
                'away_team_name': event.get('strAwayTeam', ''),
                'match_time': event.get('strTimestamp', event.get('dateEvent', '')),
                'home_score': int(home_score) if home_score else 0,
                'away_score': int(away_score) if away_score else 0,
                'status': 'finished' if event.get('strStatus') == 'Match Finished' else 'scheduled',
                'source': 'thesportsdb',
            })

        logger.info(f"TheSportsDB: {len(matches)} 场今日比赛")
        return matches

    # ── 综合数据获取 ────────────────────────────────────────────

    def get_all_real_matches(self) -> List[dict]:
        """获取所有真实比赛数据（多数据源聚合）"""
        matches = self.get_all_openligadb_matches()

        # 如果 OpenLigaDB 没返回数据，尝试 TheSportsDB
        if len(matches) < 5:
            tsdb = self.get_sportsdb_today_matches()
            existing_ids = {m['match_id'] for m in matches}
            for m in tsdb:
                if m['match_id'] not in existing_ids:
                    matches.append(m)

        return matches

    def get_combined_today_matches(self) -> List[dict]:
        """获取今日综合比赛数据"""
        today = datetime.now().strftime('%Y-%m-%d')
        matches = self.get_today_matches()

        # 补充 TheSportsDB
        tsdb = self.get_sportsdb_today_matches()
        existing = {(m.get('home_team_name', ''), m.get('away_team_name', '')) for m in matches}
        for m in tsdb:
            key = (m.get('home_team_name', ''), m.get('away_team_name', ''))
            if key not in existing and today in str(m.get('match_time', '')):
                matches.append(m)

        return matches


# ── 全局单例 ────────────────────────────────────────────────────

_data_service = None


def get_data_service() -> RealDataService:
    """获取数据服务单例"""
    global _data_service
    if _data_service is None:
        _data_service = RealDataService()
    return _data_service


# ── 测试入口 ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("真实数据服务测试")
    print("=" * 60)

    svc = RealDataService()

    # 测试1: 获取德甲比赛
    print("\n[1] 获取德甲比赛...")
    bl1 = svc.get_openligadb_league_matches('bl1')
    if bl1:
        print(f"德甲: {len(bl1)} 场")
        for m in bl1[:3]:
            score = f"{m['home_score']}-{m['away_score']}" if m['status'] != 'scheduled' else 'VS'
            status_cn = {'scheduled': '未开始', 'live': '进行中', 'finished': '已结束'}.get(m['status'], m['status'])
            print(f"  {m['home_team_name']} {score} {m['away_team_name']} [{m['match_time']}] ({status_cn})")
    else:
        print("  无数据 - API 可能不可用")

    # 测试2: 获取今日比赛
    print("\n[2] 获取今日比赛...")
    today_matches = svc.get_combined_today_matches()
    print(f"今日比赛: {len(today_matches)} 场")

    # 测试3: 球队近期战绩
    if bl1:
        first_match = bl1[0]
        print(f"\n[3] 获取 {first_match['home_team_name']} 近期战绩...")
        form = svc.get_team_recent_form(first_match['home_team_name_en'], 'bl1')
        if form['recent_results']:
            print(f"  近期: {' '.join(form['recent_results'])} (胜{form['wins']}平{form['draws']}负{form['losses']})")
        else:
            print("  无数据")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
