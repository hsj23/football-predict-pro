"""
中国体彩竞彩足球数据爬虫
数据来源优先级：
1. 中国足彩网 (zgzcw.com) - 竞彩官方数据
2. OpenLigaDB API - 国际联赛真实数据
3. TheSportsDB - 免费足球数据API
"""
import json
import time
import re
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from real_data_service import get_data_service

# 导入OpenLigaDB爬虫
try:
    from .openligadb_crawler import OpenLigaDBCrawler
    OPENLIGADB_AVAILABLE = True
except ImportError:
    OPENLIGADB_AVAILABLE = False


class ChinaLotteryCrawler:
    """中国体彩竞彩足球爬虫 - Selenium 自动化"""

    def __init__(self):
        self.driver = None

    def _init_driver(self):
        """初始化 Selenium WebDriver"""
        if self.driver:
            return

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument('--headless=new')  # 新版无头模式
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            # 自动下载和配置 ChromeDriver
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

            # 执行 CDP 命令隐藏自动化特征
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })

            self.driver.set_page_load_timeout(60)

        except Exception as e:
            print(f"初始化 Selenium 失败: {e}")
            self.driver = None

    def _close_driver(self):
        """关闭 WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def get_jczq_matches(self) -> List[Dict]:
        """获取竞彩足球实际开售的比赛 - 多数据源"""
        matches = []

        # 优先从中国足彩网获取数据
        print("正在从中国足彩网获取竞彩数据...")
        try:
            zgzcw_matches = self._fetch_from_zgzcw()
            if zgzcw_matches and len(zgzcw_matches) >= 3:
                matches = zgzcw_matches
                print(f"中国足彩网获取 {len(matches)} 场比赛")
                return matches
        except Exception as e:
            print(f"中国足彩网获取失败: {e}")

        # 从OpenLigaDB获取国际联赛数据
        if OPENLIGADB_AVAILABLE:
            print("正在从OpenLigaDB获取国际联赛数据...")
            try:
                crawler = OpenLigaDBCrawler()
                openligadb_matches = crawler.get_all_matches()
                if openligadb_matches:
                    # 过滤掉已结束的比赛，只保留未开始和进行中的
                    upcoming = [m for m in openligadb_matches if m.get('status') != 'finished']
                    if upcoming:
                        matches.extend(upcoming)
                        print(f"OpenLigaDB获取 {len(upcoming)} 场比赛")
            except Exception as e:
                print(f"OpenLigaDB获取失败: {e}")

        # 如果有足够的比赛数据，直接返回
        if len(matches) >= 5:
            return matches

        # 从配置文件读取
        print("正在从配置文件加载体彩竞彩比赛...")
        try:
            config_matches = self._load_from_config()
            if config_matches:
                matches.extend(config_matches)
                print(f"配置文件加载 {len(config_matches)} 场比赛")
        except Exception as e:
            print(f"配置文件加载失败: {e}")

        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = f"{m.get('home_team_name')}_{m.get('away_team_name')}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        return unique_matches if unique_matches else self._get_offline_matches()

    def _fetch_from_zgzcw(self) -> List[Dict]:
        """从中国足彩网获取竞彩比赛数据"""
        matches = []

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            import re

            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            try:
                driver.get('https://news.zgzcw.com/jczq/index.shtml')
                time.sleep(3)

                html = driver.page_source

                # 解析比赛数据
                pattern = r'【足球】(周[一二三四五六日]\d+)([^推]+)推荐[：:]\s*([^V]+)VS([^\s<【]+)'
                found = re.findall(pattern, html)

                seen = set()
                today = datetime.now()

                for match in found:
                    match_num = match[0]
                    league = match[1].strip()
                    home = match[2].strip().rstrip('"')
                    away = match[3].strip().rstrip('"')

                    key = f"{home}_{away}"
                    if key in seen:
                        continue
                    seen.add(key)

                    # 竞彩比赛都是未来开售的，设置为今天开始
                    # 根据比赛编号的后缀决定是今天几点
                    match_idx = int(match_num[2:]) if len(match_num) > 2 else 0
                    day_offset = 0  # 全部设为今天

                    match_date = today + timedelta(days=day_offset)
                    hour = 19 + (match_idx % 5)  # 19:00 - 23:00
                    match_time = match_date.replace(hour=hour, minute=0, second=0, microsecond=0)

                    matches.append({
                        'match_id': f"JCZQ_{match_num}_{match_date.strftime('%Y-%m-%d')}",
                        'league_name': league,
                        'home_team_name': home,
                        'away_team_name': away,
                        'match_time': match_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'scheduled',
                        'source': 'zgzcw'
                    })

            finally:
                driver.quit()

        except Exception as e:
            print(f"  中国足彩网请求失败: {e}")

        return matches

    def _load_from_config(self) -> List[Dict]:
        """从配置文件加载体彩竞彩比赛数据"""
        import os

        # 查找配置文件
        config_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        'data', 'jczq_matches.json'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        'data', 'lottery_matches.json'),
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                print(f"  读取: {os.path.basename(config_path)}")
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                matches_data = config.get('matches', [])
                matches = []

                today = datetime.now()
                today_str = today.strftime('%Y%m%d')

                for i, m in enumerate(matches_data):
                    # 解析比赛时间
                    time_str = m.get('time', '20:00')
                    try:
                        hour, minute = map(int, time_str.split(':'))
                    except:
                        hour, minute = 20, 0

                    match_time = today.replace(hour=hour, minute=minute, second=0)

                    match = {
                        'match_id': f"JCZQ{today_str}_{m.get('league', '')[:2]}_{i}",
                        'league_name': m.get('league', ''),
                        'home_team_name': m.get('home', ''),
                        'away_team_name': m.get('away', ''),
                        'match_time': match_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'scheduled',
                        'source': 'jczq_config'
                    }
                    matches.append(match)

                return matches

        return []

    def _fetch_from_openligadb(self) -> List[Dict]:
        """从 OpenLigaDB API 获取比赛数据"""
        matches = []

        import subprocess

        # 球队名称中英文映射
        team_name_map = {
            # 英超
            'Manchester City': '曼城', 'Manchester City FC': '曼城',
            'Manchester United': '曼联', 'Manchester United FC': '曼联',
            'Liverpool': '利物浦', 'FC Liverpool': '利物浦',
            'Chelsea': '切尔西', 'Chelsea FC': '切尔西',
            'Arsenal': '阿森纳', 'FC Arsenal': '阿森纳',
            'Tottenham': '热刺', 'Tottenham Hotspur': '热刺',
            'Newcastle': '纽卡斯尔', 'Newcastle United FC': '纽卡斯尔',
            'Aston Villa': '阿斯顿维拉',
            'Brighton': '布莱顿', 'Brighton & Hove Albion F.C.': '布莱顿',
            'West Ham': '西汉姆', 'West Ham United FC': '西汉姆',
            'Brentford': '布伦特福德', 'Brentford F.C.': '布伦特福德',
            'Fulham': '富勒姆', 'Fulham FC': '富勒姆',
            'Crystal Palace': '水晶宫', 'Crystal Palace FC': '水晶宫',
            'Wolverhampton': '狼队', 'Wolverhampton Wanderers FC': '狼队',
            'Everton': '埃弗顿', 'Everton FC': '埃弗顿',
            'Nottingham Forest': '诺丁汉森林',
            'Bournemouth': '伯恩茅斯', 'AFC Bournemouth': '伯恩茅斯',
            'Sheffield United': '谢菲尔德联',
            'Burnley': '伯恩利', 'Burnley FC': '伯恩利',
            'Luton Town': '卢顿', 'Luton Town FC': '卢顿',
            # 德甲
            'Bayern München': '拜仁慕尼黑', 'FC Bayern München': '拜仁慕尼黑',
            'Borussia Dortmund': '多特蒙德',
            'RB Leipzig': '莱比锡',
            'Leverkusen': '勒沃库森', 'Bayer 04 Leverkusen': '勒沃库森',
            'Eintracht Frankfurt': '法兰克福',
            'VfB Stuttgart': '斯图加特',
            'VfL Wolfsburg': '沃尔夫斯堡',
            'Borussia Mönchengladbach': '门兴格拉德巴赫',
            'SC Freiburg': '弗赖堡',
            'TSG Hoffenheim': '霍芬海姆',
            '1. FC Union Berlin': '柏林联合',
            'FC Augsburg': '奥格斯堡',
            '1. FSV Mainz 05': '美因茨',
            'SV Werder Bremen': '云达不莱梅',
            'VfL Bochum': '波鸿',
            'FC St. Pauli': '圣保利',
            '1. FC Heidenheim': '海登海姆', '1. FC Heidenheim 1846': '海登海姆',
            '1. FC Köln': '科隆',
            'Hamburger SV': '汉堡',
            # 西甲
            'Real Madrid': '皇家马德里',
            'Barcelona': '巴塞罗那', 'FC Barcelona': '巴塞罗那',
            'Atletico Madrid': '马德里竞技',
            'Sevilla': '塞维利亚', 'Sevilla FC': '塞维利亚',
            'Valencia': '瓦伦西亚', 'FC Valencia': '瓦伦西亚',
            'Villarreal': '比利亚雷亚尔', 'FC Villareal': '比利亚雷亚尔',
            'Real Sociedad': '皇家社会',
            'Real Betis': '贝蒂斯',
            'Athletic Club': '毕尔巴鄂竞技', 'Athletic Bilbao': '毕尔巴鄂竞技',
            'Getafe': '赫塔费', 'FC Getafe': '赫塔费',
            'Osasuna': '奥萨苏纳', 'CA Osasuna': '奥萨苏纳',
            'Celta Vigo': '塞尔塔',
            'Mallorca': '马洛卡', 'RCD Mallorca': '马洛卡',
            'Rayo Vallecano': '巴列卡诺',
            'Girona': '赫罗纳', 'FC Girona': '赫罗纳',
            'Almeria': '阿尔梅里亚', 'UD Almeria': '阿尔梅里亚',
            'Cádiz': '加的斯', 'FC Cádiz': '加的斯',
            'Granada': '格拉纳达', 'Granada CF': '格拉纳达',
            # 意甲
            'Juventus': '尤文图斯', 'Juventus FC': '尤文图斯',
            'AC Milan': 'AC米兰',
            'Inter': '国际米兰', 'Inter Milan': '国际米兰',
            'Napoli': '那不勒斯', 'SSC Napoli': '那不勒斯',
            'Roma': '罗马', 'AS Roma': '罗马',
            'Lazio': '拉齐奥', 'SS Lazio': '拉齐奥',
            'Atalanta': '亚特兰大', 'Atalanta BC': '亚特兰大',
            'Fiorentina': '佛罗伦萨', 'ACF Fiorentina': '佛罗伦萨',
            'Bologna': '博洛尼亚', 'Bologna FC': '博洛尼亚',
            'Torino': '都灵', 'Torino FC': '都灵',
            # 法甲
            'Paris Saint-Germain': '巴黎圣日耳曼', 'PSG': '巴黎圣日耳曼',
            'Marseille': '马赛', 'Olympique Marseille': '马赛',
            'Lyon': '里昂', 'Olympique Lyon': '里昂',
            'Monaco': '摩纳哥', 'AS Monaco': '摩纳哥',
            'Lille': '里尔', 'LOSC Lille': '里尔',
            'Nice': '尼斯', 'OGC Nice': '尼斯',
            'Lens': '朗斯', 'RC Lens': '朗斯',
            'Rennes': '雷恩', 'Stade Rennais': '雷恩',
            # 欧冠
            'Real Madrid': '皇家马德里',
            'Atletico Madrid': '马德里竞技',
        }

        # OpenLigaDB 支持的联赛
        leagues = [
            {'code': 'bl1', 'name': '德甲'},
            {'code': 'pl1', 'name': '英超'},
            {'code': 'laliga1', 'name': '西甲'},
            {'code': 'sa1', 'name': '意甲'},
            {'code': 'fl1', 'name': '法甲'},
            {'code': 'cl', 'name': '欧冠'},
            {'code': 'el', 'name': '欧联杯'},
        ]

        for league in leagues:
            try:
                url = f"https://api.openligadb.de/getmatchdata/{league['code']}"
                result = subprocess.run(
                    ['curl', '-s', '--connect-timeout', '10',
                     '-H', 'User-Agent: Mozilla/5.0',
                     url],
                    capture_output=True,
                    timeout=20
                )

                if result.returncode == 0 and result.stdout:
                    try:
                        data = json.loads(result.stdout.decode('utf-8'))
                    except:
                        continue

                    for item in data:
                        try:
                            # 翻译球队名称
                            home_team = item['team1']['teamName']
                            away_team = item['team2']['teamName']

                            # 查找中文翻译
                            home_cn = team_name_map.get(home_team, home_team)
                            away_cn = team_name_map.get(away_team, away_team)

                            # 处理比赛时间 - 使用今天或未来日期
                            match_time_str = item.get('matchDateTime', '')
                            if match_time_str:
                                try:
                                    match_dt = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                                except:
                                    match_dt = datetime.now()
                            else:
                                match_dt = datetime.now()

                            # 如果比赛时间已过，设置为明天的默认时间
                            if match_dt < datetime.now():
                                today = datetime.now()
                                match_dt = today.replace(hour=20, minute=0, second=0)
                                match_dt += timedelta(days=1)

                            match = {
                                'match_id': f"OLD_{item.get('matchID', int(time.time() * 1000) % 90000 + 10000)}",
                                'league_name': league['name'],
                                'home_team_name': home_cn,
                                'away_team_name': away_cn,
                                'home_team_name_en': home_team,
                                'away_team_name_en': away_team,
                                'match_time': match_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                'status': 'finished' if item.get('matchIsFinished') else 'scheduled',
                                'source': 'openligadb'
                            }
                            matches.append(match)
                        except:
                            continue

                    print(f"  {league['name']}: {len([m for m in matches if m['league_name'] == league['name']])} 场")

            except Exception as e:
                print(f"  {league['name']} 获取失败: {e}")

        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = f"{m['home_team_name']}_{m['away_team_name']}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        return unique_matches

    def _fetch_with_selenium(self) -> List[Dict]:
        """使用 Selenium 获取比赛数据"""
        matches = []

        self._init_driver()
        if not self.driver:
            print("无法初始化 WebDriver")
            return matches

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # 访问雷速体育即时比分
            print("正在访问雷速体育...")
            self.driver.get("https://m.leisu.com/live")

            # 等待页面完全加载
            print("等待页面加载...")
            time.sleep(8)

            # 滚动页面加载更多内容
            for i in range(3):
                self.driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)

            # 获取页面源码
            page_source = self.driver.page_source

            # 方法1: 从页面源码中提取 JSON 数据
            print("正在解析比赛数据...")

            # 查找 window.__NUXT__ 数据
            import re
            nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', page_source, re.DOTALL)
            if nuxt_match:
                try:
                    import json
                    nuxt_data = json.loads(nuxt_match.group(1).replace('undefined', 'null'))
                    # 尝试从 nuxt_data 中提取比赛
                except:
                    pass

            # 方法2: 查找所有包含 vs 的文本
            vs_pattern = r'([^\s<>]{2,15})\s*(?:VS|vs|V\.S\.)\s*([^\s<>]{2,15})'
            vs_matches = re.findall(vs_pattern, page_source)

            for home, away in vs_matches:
                if self._is_valid_team_name(home) and self._is_valid_team_name(away):
                    match = {
                        'match_id': f"leisu_{int(time.time() * 1000) % 90000 + 10000}",
                        'league_name': self._guess_league(home, away),
                        'home_team_name': home,
                        'away_team_name': away,
                        'match_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'scheduled',
                        'source': 'leisu_vs'
                    }
                    matches.append(match)

            # 方法3: 通过 DOM 元素获取
            if len(matches) < 5:
                try:
                    # 查找所有比赛相关元素
                    match_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'vs') or contains(text(), 'VS')]")

                    for elem in match_elements:
                        try:
                            text = elem.text.strip()
                            if 'VS' in text.upper() and len(text) < 50:
                                parts = re.split(r'\s*(?:VS|vs)\s*', text)
                                if len(parts) == 2:
                                    home = parts[0].strip()
                                    away = parts[1].strip()
                                    if self._is_valid_team_name(home) and self._is_valid_team_name(away):
                                        match = {
                                            'match_id': f"leisu_dom_{int(time.time() * 1000) % 90000 + 10000}",
                                            'league_name': self._guess_league(home, away),
                                            'home_team_name': home,
                                            'away_team_name': away,
                                            'match_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                            'status': 'scheduled',
                                            'source': 'leisu_dom'
                                        }
                                        matches.append(match)
                        except:
                            continue
                except Exception as e:
                    print(f"DOM 解析失败: {e}")

            print(f"从页面提取到 {len(matches)} 条数据")

        except Exception as e:
            print(f"Selenium 访问失败: {e}")

        finally:
            self._close_driver()

        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = f"{m['home_team_name']}_{m['away_team_name']}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        return unique_matches

    def _fetch_with_curl(self) -> List[Dict]:
        """使用 curl 命令获取数据"""
        matches = []

        import subprocess

        # 尝试多个数据源
        sources = [
            {
                'name': '雷速体育',
                'url': 'https://m.leisu.com/live',
                'source_id': 'leisu'
            },
            {
                'name': '500彩票',
                'url': 'https://odds.500.com/',
                'source_id': 'wubai'
            }
        ]

        for source in sources:
            try:
                print(f"正在用 curl 访问 {source['name']}...")
                result = subprocess.run(
                    ['curl', '-s', '-L', '--connect-timeout', '15',
                     '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                     source['url']],
                    capture_output=True,
                    timeout=30
                )

                if result.returncode == 0 and result.stdout:
                    # 处理编码
                    try:
                        html = result.stdout.decode('utf-8', errors='ignore')
                    except:
                        html = result.stdout.decode('gbk', errors='ignore')

                    extracted = self._extract_matches_from_html(html, source['source_id'])
                    if extracted:
                        matches.extend(extracted)
                        print(f"  {source['name']}: 提取到 {len(extracted)} 场比赛")

            except Exception as e:
                print(f"  {source['name']} curl 失败: {e}")

        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = f"{m.get('home_team_name', '')}_{m.get('away_team_name', '')}"
            if key not in seen and m.get('home_team_name') and m.get('away_team_name'):
                # 过滤掉无效的队名
                home = m.get('home_team_name', '')
                away = m.get('away_team_name', '')
                if len(home) >= 2 and len(away) >= 2 and not any(x in home for x in ['title=', 'class=', 'href=', 'id=']):
                    seen.add(key)
                    unique_matches.append(m)

        return unique_matches

    def _extract_matches_from_html(self, html: str, source: str) -> List[Dict]:
        """从 HTML 中提取比赛数据"""
        matches = []

        # 方法1: 查找 JSON 数据中的队名
        json_patterns = [
            r'"homeTeamName"\s*:\s*"([^"]+)"[^}]*"awayTeamName"\s*:\s*"([^"]+)"',
            r'"awayTeamName"\s*:\s*"([^"]+)"[^}]*"homeTeamName"\s*:\s*"([^"]+)"',
            r'"hname"\s*:\s*"([^"]+)"[^}]*"aname"\s*:\s*"([^"]+)"',
            r'"aname"\s*:\s*"([^"]+)"[^}]*"hname"\s*:\s*"([^"]+)"',
            r'"homeTeam"\s*:\s*"([^"]+)"[^}]*"awayTeam"\s*:\s*"([^"]+)"',
            r'"awayTeam"\s*:\s*"([^"]+)"[^}]*"homeTeam"\s*:\s*"([^"]+)"',
        ]

        for pattern in json_patterns:
            found = re.findall(pattern, html)
            for teams in found:
                home, away = teams[0], teams[1]
                if home and away and len(home) < 30 and len(away) < 30:
                    if self._is_valid_team_name(home) and self._is_valid_team_name(away):
                        match = {
                            'match_id': f"{source}_{int(time.time() * 1000) % 90000 + 10000}",
                            'league_name': self._guess_league(home, away),
                            'home_team_name': home,
                            'away_team_name': away,
                            'match_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'status': 'scheduled',
                            'source': source
                        }
                        matches.append(match)

        # 方法2: 查找比赛 VS 格式（在文本节点中）
        if len(matches) < 10:
            # 清理 HTML，提取纯文本
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)

            # 查找 "队名 VS 队名" 或 "队名 vs 队名"
            vs_pattern = r'([^\s]{2,10})\s+(?:VS|vs|V\.S\.|v\.s\.)\s+([^\s]{2,10})'
            found = re.findall(vs_pattern, text)

            for home, away in found:
                home = home.strip()
                away = away.strip()
                if self._is_valid_team_name(home) and self._is_valid_team_name(away):
                    match = {
                        'match_id': f"{source}_{int(time.time() * 1000) % 90000 + 10000}",
                        'league_name': self._guess_league(home, away),
                        'home_team_name': home,
                        'away_team_name': away,
                        'match_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'scheduled',
                        'source': source
                    }
                    matches.append(match)

        return matches[:50]

    def _is_valid_team_name(self, name: str) -> bool:
        """检查是否是有效的队名"""
        if not name or len(name) < 2 or len(name) > 20:
            return False

        # 排除 HTML 属性和常见无效字符
        invalid_patterns = [
            'title=', 'class=', 'href=', 'id=', 'style=', 'onclick=',
            'http://', 'https://', 'javascript:', '<', '>', '"', "'",
            'data-', 'aria-', 'role=', 'div', 'span', 'class'
        ]

        for pattern in invalid_patterns:
            if pattern.lower() in name.lower():
                return False

        # 检查是否包含中文或英文字母
        has_chinese = any('一' <= c <= '鿿' for c in name)
        has_english = any(c.isalpha() and ord(c) < 128 for c in name)

        return has_chinese or has_english

    def _parse_match_text(self, text: str) -> Optional[Dict]:
        """解析比赛文本"""
        try:
            # 尝试解析 "主队 VS 客队" 格式
            if 'VS' in text.upper():
                parts = re.split(r'\s*VS\s*', text, flags=re.IGNORECASE)
                if len(parts) >= 2:
                    home = parts[0].strip()
                    away = parts[1].strip()
                    return {
                        'match_id': f"parsed_{int(time.time() * 1000) % 90000 + 10000}",
                        'league_name': self._guess_league(home, away),
                        'home_team_name': home,
                        'away_team_name': away,
                        'match_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'scheduled'
                    }
        except:
            pass
        return None

    def _guess_league(self, home: str, away: str) -> str:
        """根据球队猜测联赛"""
        teams = {
            '英超': ['曼城', '利物浦', '阿森纳', '切尔西', '曼联', '热刺', '纽卡斯尔', '阿斯顿维拉', '布莱顿', '西汉姆', '狼队', '埃弗顿', '富勒姆', '水晶宫', '布伦特福德', '伯恩茅斯', '诺丁汉森林', '卢顿', '伯恩利', '谢菲尔德联'],
            '西甲': ['皇家马德里', '巴塞罗那', '马德里竞技', '塞维利亚', '瓦伦西亚', '比利亚雷亚尔', '皇家社会', '贝蒂斯', '毕尔巴鄂竞技', '赫塔费', '奥萨苏纳', '塞尔塔', '马洛卡', '拉斯帕尔马斯', '巴列卡诺', '赫罗纳', '阿拉维斯', '加的斯', '格拉纳达', '阿尔梅里亚'],
            '德甲': ['拜仁慕尼黑', '多特蒙德', '莱比锡', '勒沃库森', '法兰克福', '沃尔夫斯堡', '弗赖堡', '门兴格拉德巴赫', '美因茨', '霍芬海姆', '科隆', '斯图加特', '云达不莱梅', '波鸿', '奥格斯堡', '海登海姆', '达姆施塔特'],
            '意甲': ['AC米兰', '国际米兰', '尤文图斯', '罗马', '那不勒斯', '拉齐奥', '亚特兰大', '佛罗伦萨', '博洛尼亚', '都灵', '乌迪内斯', '萨索洛', '恩波利', '蒙扎', '维罗纳', '莱切', '卡利亚里', '热那亚', '弗罗西诺内', '萨勒尼塔纳'],
            '法甲': ['巴黎圣日耳曼', '马赛', '里昂', '摩纳哥', '里尔', '尼斯', '朗斯', '雷恩', '斯特拉斯堡', '南特', '蒙彼利埃', '图卢兹', '布雷斯特', '兰斯', '勒阿弗尔', '梅斯', '洛里昂', '克莱蒙'],
            '中超': ['上海申花', '北京国安', '山东泰山', '上海海港', '成都蓉城', '浙江队', '武汉三镇', '天津津门虎', '河南队', '梅州客家', '长春亚泰', '沧州雄狮', '青岛海牛', '深圳队', '南通支云', '青岛西海岸'],
            '欧冠': ['曼城', '皇家马德里', '拜仁慕尼黑', '巴塞罗那', '巴黎圣日耳曼', 'AC米兰', '国际米兰', '多特蒙德'],
            '欧联杯': ['罗马', '勒沃库森', '塞维利亚', '尤文图斯', '利物浦', '亚特兰大', 'AC米兰', '西汉姆'],
        }

        for league, team_list in teams.items():
            if any(t in home for t in team_list) or any(t in away for t in team_list):
                return league

        return '其他'

    def _get_offline_matches(self) -> List[Dict]:
        """获取比赛数据 - 优先从实时API获取"""
        matches = []

        # 从真实API获取数据
        try:
            data_svc = get_data_service()
            real_matches = data_svc.get_all_real_matches()
            if real_matches:
                # 转换为本系统格式
                for m in real_matches:
                    matches.append({
                        'match_id': m['match_id'],
                        'league_name': m['league_name'],
                        'home_team_name': m['home_team_name'],
                        'away_team_name': m['away_team_name'],
                        'match_time': m['match_time'].replace(' ', '  ') if len(m['match_time']) <= 16 else m['match_time'],
                        'status': m.get('status', 'scheduled'),
                        'source': m.get('source', 'real_api'),
                    })
                print(f"从真实API获取 {len(matches)} 场比赛")
                return matches
        except Exception as e:
            print(f"真实API获取失败: {e}")

        # 如果API不可用，返回空列表（不生成假数据）
        print("未能获取到比赛数据，请检查网络连接")
        return []

    def get_history_results(self, days: int = 30) -> List[Dict]:
        """获取历史开奖结果 - 优先使用真实数据"""
        results = []

        # 尝试从OpenLigaDB获取真实历史数据
        if OPENLIGADB_AVAILABLE:
            try:
                print("正在从OpenLigaDB获取历史比赛数据...")
                crawler = OpenLigaDBCrawler()

                for league_code in ['bl1', 'pl1', 'laliga1', 'sa1', 'fl1']:
                    try:
                        historical = crawler.get_historical_matches(league_code, '2024', days=days)
                        for match in historical:
                            if not match.get('is_finished'):
                                continue

                            home_score = match.get('home_score', 0)
                            away_score = match.get('away_score', 0)

                            if home_score > away_score:
                                actual_result = 'home'
                            elif home_score < away_score:
                                actual_result = 'away'
                            else:
                                actual_result = 'draw'

                            # 简单预测（基于球队名称判断）
                            pred_result = self._simple_predict(match.get('home_team_name', ''), match.get('away_team_name', ''))
                            is_correct = 1 if pred_result == actual_result else 2

                            results.append({
                                'match_id': match.get('match_id', f"HIST_{int(time.time() * 1000) % 10000}"),
                                'match_date': match.get('match_time', '')[:10],
                                'league': match.get('league_name', ''),
                                'home_team': match.get('home_team_name', ''),
                                'away_team': match.get('away_team_name', ''),
                                'prediction_result': pred_result,
                                'prediction_name': {'home': '主胜', 'draw': '平局', 'away': '客胜'}[pred_result],
                                'confidence': 70,
                                'actual_result': actual_result,
                                'actual_score': f"{home_score}-{away_score}",
                                'home_score': home_score,
                                'away_score': away_score,
                                'is_correct': is_correct
                            })
                    except Exception as e:
                        continue

                if results:
                    print(f"从OpenLigaDB获取 {len(results)} 条历史记录")
                    return results
            except Exception as e:
                print(f"OpenLigaDB历史数据获取失败: {e}")

        # 如果没有真实数据，使用智能模拟数据
        print("使用智能模拟历史数据...")
        return self._generate_smart_history(days)

    def _simple_predict(self, home_team: str, away_team: str) -> str:
        """
        简单预测 - 基于球队实力分析
        改进：使用确定性预测，提高准确率
        """
        team_strength = {
            '曼城': 95, '利物浦': 92, '阿森纳': 92, '切尔西': 85, '曼联': 83, '热刺': 82,
            '纽卡斯尔': 84, '阿斯顿维拉': 80, '布莱顿': 78,
            '皇家马德里': 96, '巴塞罗那': 92, '马德里竞技': 88, '塞维利亚': 80,
            '拜仁慕尼黑': 95, '多特蒙德': 88, '勒沃库森': 93, '莱比锡': 85,
            'AC米兰': 86, '国际米兰': 90, '尤文图斯': 85, '罗马': 80, '那不勒斯': 86, '亚特兰大': 84,
            '巴黎圣日耳曼': 94, '马赛': 78, '摩纳哥': 80, '里昂': 76, '里尔': 78, '尼斯': 74,
            '斯图加特': 80, '法兰克福': 78, '皇家社会': 81, '贝蒂斯': 77,
        }

        home_strength = team_strength.get(home_team, 70)
        away_strength = team_strength.get(away_team, 70)

        # 主场优势 +5
        home_strength += 5

        # 使用确定性预测（不使用随机数）
        strength_diff = home_strength - away_strength

        if strength_diff > 12:
            return 'home'
        elif strength_diff < -12:
            return 'away'
        else:
            # 实力接近时，根据小幅差距判断
            if strength_diff > 3:
                return 'home'
            elif strength_diff < -3:
                return 'away'
            else:
                return 'draw'

    def _generate_smart_history(self, days: int) -> List[Dict]:
        """获取历史比赛数据 - 从真实API获取已完成的比赛"""
        results = []

        team_strength = {
            '曼城': 95, '利物浦': 92, '阿森纳': 92, '切尔西': 85, '曼联': 83, '热刺': 82,
            '纽卡斯尔': 84, '阿斯顿维拉': 80,
            '皇家马德里': 96, '巴塞罗那': 92, '马德里竞技': 88, '塞维利亚': 80,
            '皇家社会': 81, '贝蒂斯': 77,
            '拜仁慕尼黑': 95, '多特蒙德': 88, '勒沃库森': 93, '莱比锡': 85,
            '斯图加特': 80, '法兰克福': 78,
            'AC米兰': 86, '国际米兰': 90, '尤文图斯': 85, '罗马': 80,
            '那不勒斯': 86, '亚特兰大': 84,
            '巴黎圣日耳曼': 94, '马赛': 78, '里昂': 76, '摩纳哥': 80,
            '里尔': 78, '尼斯': 74,
        }

        # 尝试从真实API获取已完成比赛
        try:
            data_svc = get_data_service()
            all_matches = data_svc.get_all_real_matches()
            finished = [m for m in all_matches if m.get('is_finished')]

            for m in finished:
                home = m['home_team_name']
                away = m['away_team_name']
                home_score = m.get('home_score', 0)
                away_score = m.get('away_score', 0)

                if home_score > away_score:
                    actual_result = 'home'
                elif home_score < away_score:
                    actual_result = 'away'
                else:
                    actual_result = 'draw'

                # 基于实力分析的预测
                home_strength_val = team_strength.get(home, 70)
                away_strength_val = team_strength.get(away, 70)
                pred_result = self._simple_predict(home, away)
                is_correct = 1 if pred_result == actual_result else 2

                results.append({
                    'match_id': m['match_id'],
                    'match_date': m['match_time'][:10] if m['match_time'] else '',
                    'league': m['league_name'],
                    'home_team': home,
                    'away_team': away,
                    'prediction_result': pred_result,
                    'prediction_name': {'home': '主胜', 'draw': '平局', 'away': '客胜'}[pred_result],
                    'confidence': 65 + min(abs(home_strength_val - away_strength_val), 20),
                    'actual_result': actual_result,
                    'actual_score': f"{home_score}-{away_score}",
                    'home_score': home_score,
                    'away_score': away_score,
                    'is_correct': is_correct,
                })

            if results:
                print(f"从真实API获取 {len(results)} 条历史记录")
                return results
        except Exception as e:
            print(f"真实API历史数据获取失败: {e}")

        print("未能获取真实历史数据，返回空结果")
        return []

    def save_to_database(self, matches: List[Dict], results: List[Dict] = None):
        """保存数据到数据库"""
        try:
            from app.db_helper import db_cursor

            with db_cursor() as cursor:
                cursor.execute('DELETE FROM prediction_history')
                cursor.execute('DELETE FROM matches')
                print("已清空旧数据")

                for m in matches:
                    cursor.execute("""
                        INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (m['match_id'], m['league_name'], m['home_team_name'],
                          m['away_team_name'], m['match_time'], m.get('status', 'scheduled')))

                if results:
                    for r in results:
                        cursor.execute("""
                            INSERT INTO prediction_history
                            (match_id, match_date, league, home_team, away_team,
                             prediction_result, prediction_name, confidence,
                             actual_result, actual_score, home_score, away_score, is_correct)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (r['match_id'], r['match_date'], r['league'], r['home_team'], r['away_team'],
                              r['prediction_result'], r['prediction_name'], r['confidence'],
                              r['actual_result'], r['actual_score'], r['home_score'], r['away_score'],
                              r['is_correct']))

            print(f"已保存竞彩比赛 {len(matches)} 场")
            if results:
                print(f"已保存历史结果 {len(results)} 条")

        except Exception as e:
            print(f"保存数据库失败: {e}")


def main():
    print("=" * 50)
    print("中国体彩竞彩足球数据爬虫")
    print("=" * 50)

    crawler = ChinaLotteryCrawler()

    print("\n[1] 获取今日竞彩比赛...")
    matches = crawler.get_jczq_matches()

    print("\n[2] 获取历史开奖结果...")
    results = crawler.get_history_results(days=30)

    print("\n[3] 保存到数据库...")
    crawler.save_to_database(matches, results)

    correct = sum(1 for r in results if r['is_correct'] == 1)
    wrong = sum(1 for r in results if r['is_correct'] == 2)
    accuracy = round(correct / (correct + wrong) * 100, 1) if (correct + wrong) > 0 else 0

    print("\n" + "=" * 50)
    print("数据更新完成!")
    print("=" * 50)
    print(f"竞彩比赛: {len(matches)} 场")
    print(f"历史结果: {len(results)} 条")
    print(f"准确率: {accuracy}%")


if __name__ == "__main__":
    main()
