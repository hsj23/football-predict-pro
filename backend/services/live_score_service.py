"""
实时比分服务
获取今日比赛的实时比分和状态
"""
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LiveScoreService:
    """实时比分服务"""

    # 中国足彩网数据源
    ZGZCW_URL = "https://www.zgzcw.com/"
    ZGZCW_MATCH_URL = "https://www.zgzcw.com/match/"

    # OpenLigaDB API（备用）
    OPENLIGADB_URL = "https://api.openligadb.de"

    # 联赛名称映射
    LEAGUE_NAMES = {
        '英超': '英格兰超级联赛',
        '西甲': '西班牙甲级联赛',
        '德甲': '德国甲级联赛',
        '意甲': '意大利甲级联赛',
        '法甲': '法国甲级联赛',
        '中超': '中国超级联赛',
        '欧冠': '欧洲冠军联赛',
        '欧联': '欧洲联赛',
    }

    def __init__(self):
        self.timeout = 30
        self._cache = {}
        self._cache_time = 0
        self.cache_duration = 60  # 缓存60秒

    def _make_request(self, url: str, use_selenium: bool = False) -> Optional[str]:
        """发送HTTP请求"""
        try:
            if use_selenium:
                return self._selenium_request(url)
            else:
                result = subprocess.run(
                    ['curl', '-s', '-L', '--connect-timeout', '15',
                     '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                     '-H', 'Accept: text/html,application/xhtml+xml',
                     url],
                    capture_output=True,
                    timeout=self.timeout
                )
                if result.returncode == 0:
                    return result.stdout.decode('utf-8', errors='ignore')
                return None
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return None

    def _selenium_request(self, url: str) -> Optional[str]:
        """使用Selenium获取动态页面"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)

            try:
                driver.get(url)
                time.sleep(3)
                html = driver.page_source
                return html
            finally:
                driver.quit()

        except Exception as e:
            logger.error(f"Selenium请求失败: {e}")
            return None

    def get_today_matches(self) -> List[Dict]:
        """获取今日所有比赛"""
        cache_key = 'today_matches'

        # 检查缓存
        if self._is_cache_valid(cache_key):
            return self._cache.get(cache_key, [])

        matches = []

        # 优先从中国足彩网获取
        try:
            zgzcw_matches = self._fetch_from_zgzcw()
            if zgzcw_matches:
                matches.extend(zgzcw_matches)
                logger.info(f"从中国足彩网获取 {len(zgzcw_matches)} 场比赛")
        except Exception as e:
            logger.error(f"中国足彩网获取失败: {e}")

        # 补充OpenLigaDB数据
        if len(matches) < 5:
            try:
                openligadb_matches = self._fetch_from_openligadb()
                if openligadb_matches:
                    matches.extend(openligadb_matches)
                    logger.info(f"从OpenLigaDB获取 {len(openligadb_matches)} 场比赛")
            except Exception as e:
                logger.error(f"OpenLigaDB获取失败: {e}")

        # 更新缓存
        self._update_cache(cache_key, matches)

        return matches

    def _fetch_from_zgzcw(self) -> List[Dict]:
        """从中国足彩网获取比赛数据"""
        matches = []

        # 使用Selenium获取动态内容
        html = self._selenium_request('https://www.zgzcw.com/')
        if not html:
            return matches

        import re

        # 解析比赛数据 - 使用更精确的正则
        # 匹配比赛格式：【足球】周X001 主队 VS 客队
        pattern = r'【足球】(周[一二三四五六日]\d+)([^推【]+)推荐[：:]\s*([^V【]+)VS([^\s【<]+)'
        found = re.findall(pattern, html)

        today = datetime.now()

        for match in found:
            try:
                match_num = match[0].strip()
                league = match[1].strip()
                home = match[2].strip().rstrip('"').rstrip("'")
                away = match[3].strip().rstrip('"').rstrip("'")

                # 清理联赛名称
                league = league.replace('推荐', '').strip()

                if not home or not away or len(home) < 2 or len(away) < 2:
                    continue

                # 比赛时间（竞彩比赛通常在下午到晚上）
                match_idx = int(match_num[2:]) if len(match_num) > 2 else 1
                hour = 15 + (match_idx % 8)  # 15:00 - 22:00

                match_time = today.replace(hour=hour, minute=0, second=0, microsecond=0)

                matches.append({
                    'match_id': f"ZGZCW_{match_num}",
                    'league_name': league,
                    'home_team_name': home,
                    'away_team_name': away,
                    'match_time': match_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'home_score': 0,
                    'away_score': 0,
                    'status': 'scheduled',
                    'minute': 0,
                    'source': 'zgzcw'
                })
            except Exception as e:
                continue

        # 去重
        seen = set()
        unique_matches = []
        for m in matches:
            key = f"{m['home_team_name']}_{m['away_team_name']}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        return unique_matches

    def _fetch_from_openligadb(self) -> List[Dict]:
        """从OpenLigaDB获取比赛数据"""
        matches = []
        today = datetime.now().strftime('%Y-%m-%d')

        leagues = ['bl1', 'bl2', 'pl1', 'laliga1', 'sa1', 'fl1']

        for league in leagues:
            try:
                url = f"{self.OPENLIGADB_URL}/getmatchdata/{league}"
                result = subprocess.run(
                    ['curl', '-s', '--connect-timeout', '10', url],
                    capture_output=True, timeout=20
                )

                if result.returncode != 0 or not result.stdout:
                    continue

                data = json.loads(result.stdout.decode('utf-8'))

                # 球队名称映射
                team_map = {
                    'Bayern München': '拜仁慕尼黑',
                    'Borussia Dortmund': '多特蒙德',
                    'RB Leipzig': '莱比锡',
                    'Leverkusen': '勒沃库森',
                    'Manchester City': '曼城',
                    'Liverpool': '利物浦',
                    'Arsenal': '阿森纳',
                    'Chelsea': '切尔西',
                    'Real Madrid': '皇家马德里',
                    'Barcelona': '巴塞罗那',
                    'Juventus': '尤文图斯',
                    'AC Milan': 'AC米兰',
                    'Inter': '国际米兰',
                    'Paris Saint-Germain': '巴黎圣日耳曼',
                }

                league_names = {
                    'bl1': '德甲', 'bl2': '德乙', 'pl1': '英超',
                    'laliga1': '西甲', 'sa1': '意甲', 'fl1': '法甲'
                }

                for item in data:
                    try:
                        match_time_str = item.get('matchDateTime', '')
                        if today not in match_time_str:
                            continue

                        home_en = item.get('team1', {}).get('teamName', '')
                        away_en = item.get('team2', {}).get('teamName', '')

                        home = team_map.get(home_en, home_en)
                        away = team_map.get(away_en, away_en)

                        results = item.get('matchResults', [])
                        home_score = results[-1].get('pointsTeam1', 0) if results else 0
                        away_score = results[-1].get('pointsTeam2', 0) if results else 0

                        is_finished = item.get('matchIsFinished', False)
                        match_minute = item.get('matchMinute', 0)

                        status = 'finished' if is_finished else ('live' if match_minute > 0 else 'scheduled')

                        matches.append({
                            'match_id': f"OLD_{item.get('matchID')}",
                            'league_name': league_names.get(league, league),
                            'home_team_name': home,
                            'away_team_name': away,
                            'match_time': match_time_str,
                            'home_score': home_score,
                            'away_score': away_score,
                            'status': status,
                            'minute': match_minute,
                            'source': 'openligadb'
                        })
                    except:
                        continue

            except Exception as e:
                logger.error(f"OpenLigaDB {league} 获取失败: {e}")
                continue

        return matches

    def get_live_scores(self) -> List[Dict]:
        """获取正在进行的比赛比分"""
        matches = self.get_today_matches()
        live_matches = [m for m in matches if m.get('status') == 'live']
        return live_matches

    def get_match_details(self, match_id: str) -> Optional[Dict]:
        """获取单场比赛详情"""
        matches = self.get_today_matches()

        for match in matches:
            if match.get('match_id') == match_id:
                return match

        return None

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False

        elapsed = time.time() - self._cache_time
        return elapsed < self.cache_duration

    def _update_cache(self, key: str, data: any):
        """更新缓存"""
        self._cache[key] = data
        self._cache_time = time.time()


def test_live_score():
    """测试实时比分服务"""
    print("=" * 60)
    print("实时比分服务测试")
    print("=" * 60)

    service = LiveScoreService()

    print("\n[1] 获取今日比赛...")
    matches = service.get_today_matches()
    print(f"今日比赛: {len(matches)} 场")

    if matches:
        print("\n比赛列表:")
        for m in matches[:10]:
            status_text = {
                'scheduled': '未开始',
                'live': '进行中',
                'finished': '已结束'
            }.get(m['status'], m['status'])

            score = f"{m['home_score']}-{m['away_score']}" if m['status'] != 'scheduled' else 'VS'
            minute = f" {m.get('minute', 0)}'" if m['status'] == 'live' else ''

            print(f"  [{m['league_name']}] {m['home_team_name']} {score} {m['away_team_name']} ({status_text}{minute})")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_live_score()
