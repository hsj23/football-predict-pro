"""
OpenLigaDB API 爬虫 - 获取真实足球比赛数据
免费API，无需API Key
支持联赛：德甲、德乙、英超、西甲、意甲、法甲、欧冠、欧联杯
"""
import json
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenLigaDBCrawler:
    """OpenLigaDB API 爬虫 - 获取真实足球数据"""

    BASE_URL = "https://api.openligadb.de"

    # 联赛代码映射
    LEAGUES = {
        'bl1': {'name': '德甲', 'country': '德国'},
        'bl2': {'name': '德乙', 'country': '德国'},
        'bl3': {'name': '德丙', 'country': '德国'},
        'pl1': {'name': '英超', 'country': '英格兰'},
        'laliga1': {'name': '西甲', 'country': '西班牙'},
        'sa1': {'name': '意甲', 'country': '意大利'},
        'fl1': {'name': '法甲', 'country': '法国'},
        'cl': {'name': '欧冠', 'country': '欧洲'},
        'el': {'name': '欧联杯', 'country': '欧洲'},
    }

    # 球队名称中英文映射
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
        'Wolverhampton': '狼队', 'Wolverhampton Wanderers': '狼队', 'Wolverhampton Wanderers FC': '狼队',
        'Everton': '埃弗顿', 'Everton FC': '埃弗顿',
        'Nottingham Forest': '诺丁汉森林', 'Nottingham': '诺丁汉森林',
        'Bournemouth': '伯恩茅斯', 'AFC Bournemouth': '伯恩茅斯',
        'Sheffield United': '谢菲尔德联',
        'Burnley': '伯恩利', 'Burnley FC': '伯恩利',
        'Luton Town': '卢顿', 'Luton': '卢顿',
        'Ipswich Town': '伊普斯维奇', 'Ipswich': '伊普斯维奇',
        'Leicester City': '莱斯特城', 'Leicester': '莱斯特城',
        'Southampton': '南安普顿',
        'Wolves': '狼队',
        # 德甲
        'Bayern München': '拜仁慕尼黑', 'FC Bayern München': '拜仁慕尼黑', 'Bayern Munich': '拜仁慕尼黑',
        'Borussia Dortmund': '多特蒙德', 'Dortmund': '多特蒙德',
        'RB Leipzig': '莱比锡', 'RasenBallsport Leipzig': '莱比锡',
        'Leverkusen': '勒沃库森', 'Bayer 04 Leverkusen': '勒沃库森', 'Bayer Leverkusen': '勒沃库森',
        'Eintracht Frankfurt': '法兰克福', 'Frankfurt': '法兰克福',
        'VfB Stuttgart': '斯图加特', 'Stuttgart': '斯图加特',
        'VfL Wolfsburg': '沃尔夫斯堡', 'Wolfsburg': '沃尔夫斯堡',
        'Borussia Mönchengladbach': '门兴格拉德巴赫', 'Mönchengladbach': '门兴格拉德巴赫', 'Gladbach': '门兴格拉德巴赫',
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
        'Frosinone': '弗罗西诺内', 'Frosinone Calcio': '弗罗西诺内',
        'Salernitana': '萨勒尼塔纳', 'US Salernitana': '萨勒尼塔纳',
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
    }

    def __init__(self):
        self.timeout = 30

    def _make_request(self, url: str) -> Optional[Dict]:
        """发送HTTP请求"""
        try:
            result = subprocess.run(
                ['curl', '-s', '--connect-timeout', '15',
                 '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                 '-H', 'Accept: application/json',
                 url],
                capture_output=True,
                timeout=self.timeout
            )

            if result.returncode == 0 and result.stdout:
                try:
                    return json.loads(result.stdout.decode('utf-8'))
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}")
                    return None
            else:
                logger.error(f"请求失败: {result.stderr.decode('utf-8', errors='ignore')}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"请求超时: {url}")
            return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    def _translate_team_name(self, name: str) -> str:
        """翻译球队名称为中文"""
        return self.TEAM_NAME_MAP.get(name, name)

    def get_current_matches(self, league_code: str) -> List[Dict]:
        """获取联赛当前轮次比赛"""
        url = f"{self.BASE_URL}/getmatchdata/{league_code}"
        data = self._make_request(url)

        if not data:
            logger.warning(f"获取 {league_code} 数据失败")
            return []

        matches = []
        for item in data:
            try:
                match = self._parse_match(item, league_code)
                if match:
                    matches.append(match)
            except Exception as e:
                logger.error(f"解析比赛失败: {e}")
                continue

        logger.info(f"获取 {self.LEAGUES.get(league_code, {}).get('name', league_code)} {len(matches)} 场比赛")
        return matches

    def get_matches_by_date(self, league_code: str, date_str: str) -> List[Dict]:
        """获取指定日期的比赛"""
        url = f"{self.BASE_URL}/getmatchdata/{league_code}/{date_str}"
        data = self._make_request(url)

        if not data:
            return []

        matches = []
        for item in data:
            try:
                match = self._parse_match(item, league_code)
                if match:
                    matches.append(match)
            except Exception as e:
                logger.error(f"解析比赛失败: {e}")
                continue

        return matches

    def get_match_details(self, match_id: int) -> Optional[Dict]:
        """获取比赛详情"""
        url = f"{self.BASE_URL}/getmatchdata/{match_id}"
        data = self._make_request(url)

        if not data:
            return None

        return self._parse_match(data, None)

    def get_all_matches(self) -> List[Dict]:
        """获取所有联赛的比赛"""
        all_matches = []
        for league_code in self.LEAGUES.keys():
            try:
                matches = self.get_current_matches(league_code)
                all_matches.extend(matches)
            except Exception as e:
                logger.error(f"获取 {league_code} 失败: {e}")
                continue
        return all_matches

    def get_today_matches(self) -> List[Dict]:
        """获取今日比赛"""
        today = datetime.now().strftime('%Y-%m-%d')
        all_matches = []

        for league_code in self.LEAGUES.keys():
            try:
                url = f"{self.BASE_URL}/getmatchdata/{league_code}"
                data = self._make_request(url)

                if not data:
                    continue

                for item in data:
                    try:
                        match_time_str = item.get('matchDateTime', '')
                        if today in match_time_str:
                            match = self._parse_match(item, league_code)
                            if match:
                                all_matches.append(match)
                    except:
                        continue
            except Exception as e:
                logger.error(f"获取 {league_code} 今日比赛失败: {e}")
                continue

        return all_matches

    def _parse_match(self, item: Dict, league_code: Optional[str] = None) -> Optional[Dict]:
        """解析比赛数据"""
        try:
            match_id = item.get('matchID')
            match_time_str = item.get('matchDateTime', '')

            # 解析比赛时间
            try:
                if 'T' in match_time_str:
                    match_dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                else:
                    match_dt = datetime.fromisoformat(match_time_str)
                match_time = match_dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                match_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 球队信息
            team1 = item.get('team1', {})
            team2 = item.get('team2', {})
            home_team_en = team1.get('teamName', '')
            away_team_en = team2.get('teamName', '')
            home_team = self._translate_team_name(home_team_en)
            away_team = self._translate_team_name(away_team_en)

            # 联赛信息
            league_info = self.LEAGUES.get(league_code, {}) if league_code else {}
            league_name = item.get('leagueName', league_info.get('name', '未知联赛'))

            # 比赛状态
            is_finished = item.get('matchIsFinished', False)

            # 比分
            results = item.get('matchResults', [])
            home_score = 0
            away_score = 0

            if results:
                # 取最新比分
                latest_result = results[-1]
                home_score = latest_result.get('pointsTeam1', 0)
                away_score = latest_result.get('pointsTeam2', 0)

            # 比赛状态
            if is_finished:
                status = 'finished'
            elif home_score > 0 or away_score > 0:
                status = 'live'
            else:
                status = 'scheduled'

            return {
                'match_id': f"OLD_{match_id}",
                'league_code': league_code,
                'league_name': league_name,
                'home_team_name': home_team,
                'away_team_name': away_team,
                'home_team_name_en': home_team_en,
                'away_team_name_en': away_team_en,
                'match_time': match_time,
                'status': status,
                'home_score': home_score,
                'away_score': away_score,
                'is_finished': is_finished,
                'source': 'openligadb'
            }

        except Exception as e:
            logger.error(f"解析比赛数据失败: {e}")
            return None

    def get_historical_matches(self, league_code: str, season: str, days: int = 365) -> List[Dict]:
        """获取历史比赛数据用于模型训练"""
        url = f"{self.BASE_URL}/getmatchdata/{league_code}/{season}"
        data = self._make_request(url)

        if not data:
            logger.warning(f"获取 {league_code} {season} 历史数据失败")
            return []

        matches = []
        cutoff_date = datetime.now() - timedelta(days=days)

        for item in data:
            try:
                match = self._parse_match(item, league_code)
                if match and match.get('is_finished'):
                    match_time = datetime.strptime(match['match_time'][:10], '%Y-%m-%d')
                    if match_time >= cutoff_date:
                        matches.append(match)
            except:
                continue

        logger.info(f"获取 {league_code} {season} 历史比赛 {len(matches)} 场")
        return matches

    def get_available_seasons(self, league_code: str) -> List[str]:
        """获取可用的赛季列表"""
        url = f"{self.BASE_URL}/getavailableleagues"
        data = self._make_request(url)

        if not data:
            return []

        seasons = []
        for league in data:
            if league.get('leagueShortcut') == league_code:
                seasons.append(league.get('leagueSeason'))

        return seasons


def main():
    """测试爬虫"""
    print("=" * 60)
    print("OpenLigaDB 真实数据爬虫测试")
    print("=" * 60)

    crawler = OpenLigaDBCrawler()

    # 测试获取德甲比赛
    print("\n[1] 获取德甲当前比赛...")
    matches = crawler.get_current_matches('bl1')
    print(f"获取到 {len(matches)} 场比赛")

    if matches:
        print("\n前3场比赛:")
        for m in matches[:3]:
            status_text = {
                'scheduled': '未开始',
                'live': '进行中',
                'finished': '已结束'
            }.get(m['status'], m['status'])
            score = f"{m['home_score']}-{m['away_score']}" if m['status'] != 'scheduled' else 'VS'
            print(f"  [{m['league_name']}] {m['home_team_name']} {score} {m['away_team_name']} ({status_text})")

    # 测试获取今日比赛
    print("\n[2] 获取今日所有比赛...")
    today_matches = crawler.get_today_matches()
    print(f"今日比赛 {len(today_matches)} 场")

    # 测试获取所有联赛
    print("\n[3] 获取所有联赛比赛...")
    all_matches = crawler.get_all_matches()
    print(f"总共获取 {len(all_matches)} 场比赛")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
