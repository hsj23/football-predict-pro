"""
中国体彩官方API数据采集器
数据来源: webapi.sporttery.cn (官方竞彩足球API)
提供: 历史比赛结果 + SP赔率(胜平负)
"""
import requests
import json
import time
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry"
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'sporttery_odds.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.sporttery.cn/',
    'Accept': 'application/json',
}


def parse_score(sections_no_999: str) -> str:
    """解析比分格式: '1:0' 或 '0:1,1:1' (半场:全场) → 返回全场比分"""
    if not sections_no_999:
        return ""
    parts = sections_no_999.split(',')
    # 最后一个比分是全场
    full_score = parts[-1].strip()
    return full_score


def fetch_page(page: int, begin_date: str, end_date: str) -> dict:
    """获取一页数据"""
    params = {
        'matchPage': page,
        'matchBeginDate': begin_date,
        'matchEndDate': end_date,
    }
    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning(f"第{page}页 HTTP {resp.status_code}")
            return {}
    except Exception as e:
        logger.error(f"第{page}页请求失败: {e}")
        return {}


def fetch_all_results(begin_date: str = '2026-01-01', end_date: str = None) -> list:
    """获取指定日期范围内的所有比赛结果"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    logger.info(f"获取 {begin_date} ~ {end_date} 的比赛数据...")

    # 先获取第一页，确定总页数
    first_page = fetch_page(1, begin_date, end_date)
    value = first_page.get('value', {})
    total_pages = value.get('pages', 0)
    total_count = value.get('resultCount', value.get('total', 0))

    logger.info(f"共 {total_count} 条结果, {total_pages} 页")

    all_matches = []

    for page in range(1, min(total_pages + 1, 101)):  # 最多100页
        if page > 1:
            time.sleep(0.3)  # 请求间隔

        data = fetch_page(page, begin_date, end_date) if page > 1 else first_page
        value = data.get('value', {})
        match_results = value.get('matchResult', [])

        for m in match_results:
            try:
                home = m.get('allHomeTeam', m.get('homeTeam', ''))
                away = m.get('allAwayTeam', m.get('awayTeam', ''))
                league = m.get('leagueName', m.get('leagueNameAbbr', ''))
                match_date = m.get('matchDate', '')
                match_num = m.get('matchNumStr', '')

                # SP赔率
                h_odds = m.get('h', '')
                d_odds = m.get('d', '')
                a_odds = m.get('a', '')

                # 比分
                score_raw = m.get('sectionsNo999', '')
                full_score = parse_score(score_raw)

                # 结果状态
                result_status = m.get('matchResultStatus', '')
                win_flag = m.get('winFlag', '')

                if not home or not away:
                    continue

                # 只有有比分的才保留
                if not full_score or ':' not in full_score:
                    continue

                # 验证赔率
                try:
                    odds = [float(h_odds), float(d_odds), float(a_odds)]
                except (ValueError, TypeError):
                    odds = None

                all_matches.append({
                    'home': home,
                    'away': away,
                    'league': league,
                    'date': match_date,
                    'match_num': match_num,
                    'odds': odds,
                    'full_score': full_score,
                    'win_flag': win_flag,
                    'source': 'sporttery_api',
                })

            except Exception as e:
                continue

        if page % 10 == 0:
            logger.info(f"  进度: {page}/{total_pages} 页, 已收集 {len(all_matches)} 场")

    logger.info(f"共收集 {len(all_matches)} 场比赛 (含赔率)")

    # 去重
    seen = set()
    unique = []
    for m in all_matches:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.info(f"去重后: {len(unique)} 场")

    return unique


def main():
    """主函数: 抓取2026年全年数据"""
    logger.info("=" * 60)
    logger.info("开始从体彩官方API抓取历史数据...")
    logger.info("=" * 60)

    # 逐月抓取(避免单次请求数据量过大)
    all_data = []
    months = [
        ('2026-01-01', '2026-01-31'),
        ('2026-02-01', '2026-02-28'),
        ('2026-03-01', '2026-03-31'),
        ('2026-04-01', '2026-04-30'),
        ('2026-05-01', '2026-05-31'),
        ('2026-06-01', '2026-06-30'),
    ]

    for begin, end in months:
        matches = fetch_all_results(begin, end)
        all_data.extend(matches)
        logger.info(f"  {begin} ~ {end}: {len(matches)} 场")

    # 去重
    seen = set()
    unique = []
    for m in all_data:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    logger.info(f"\n总计: {len(unique)} 场唯一比赛")

    # 统计
    with_odds = sum(1 for m in unique if m.get('odds') and len(m['odds']) == 3)
    logger.info(f"含赔率: {with_odds} 场")

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    logger.info(f"数据已保存: {OUTPUT_FILE}")

    # 同时合并到 training_data.json
    train_file = os.path.join(DATA_DIR, 'training_data.json')
    if os.path.exists(train_file):
        with open(train_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

        # 合并
        existing_keys = {f"{m.get('home','')}_{m.get('away','')}_{m.get('date','')}" for m in existing}
        new_count = 0
        for m in unique:
            key = f"{m['home']}_{m['away']}_{m['date']}"
            if key not in existing_keys:
                existing.append(m)
                existing_keys.add(key)
                new_count += 1

        with open(train_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        logger.info(f"合并到 training_data.json: 新增 {new_count} 场, 总计 {len(existing)} 场")

    return unique


if __name__ == "__main__":
    main()
