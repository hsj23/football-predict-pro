"""
从500.com扒取历史足球比赛数据（含盘口、比分）
数据源：https://live.500.com/wanchang.php?e=YYYY-MM-DD
"""
import urllib.request, urllib.error, re, ssl, json, time, os, sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'history_500.json')

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

proxy = urllib.request.ProxyHandler({'http': 'http://127.0.0.1:7892', 'https': 'http://127.0.0.1:7892'})
opener = urllib.request.build_opener(proxy)
urllib.request.install_opener(opener)

COOKIE = 'ck_user2=bWhwNTc3ODEw; ck_user_utf8=mhp577810; token=MjAyNjA2MTIwMDAwNzk4NWUxNzM4MTk5YmFhODg2NzlmNTc4MWQxZTU0Y2UxYTk1; token_user=bWhwNTc3ODEw; usercheck=MjAyNjA2MTIwMDAwNzk4NTA5NmU0MDc2YzU0YTZmY2FlMmMxY2FmMzc3ZTI5MjQ1; isautologin=1; isagree=1'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Cookie': COOKIE,
    'Referer': 'https://live.500.com/',
}

# 非足球关键词（出现在联赛名中则跳过）
NON_FOOTBALL = ['篮球','棒球','网球','排球','冰球','橄榄球','斯诺克','飞镖','赛车','电竞',
    'NBA','NFL','MLB','NHL','PBA','CBA','F1']


def is_football(league_name):
    """排除明显非足球的联赛"""
    if not league_name:
        return False
    for kw in NON_FOOTBALL:
        if kw.upper() in league_name.upper():
            return False
    return True


def scrape_date(date_str):
    """爬取指定日期的完场比赛，带重试"""
    url = f'https://live.500.com/wanchang.php?e={date_str}'

    for attempt in range(3):
        try:
            # 轮换 UA
            hdrs = dict(HEADERS)
            ua_list = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            ]
            hdrs['User-Agent'] = ua_list[attempt % len(ua_list)]

            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as resp:
                html = resp.read().decode('gbk', errors='ignore')
            break
        except urllib.error.HTTPError as e:
            if attempt < 2:
                time.sleep(3 + attempt * 2)  # 渐进延迟
                continue
            return [], f'HTTP {e.code}'
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            return [], str(e)

    tbody_match = re.search(r'<tbody>(.*?)</tbody>', html, re.DOTALL)
    if not tbody_match:
        return [], "no tbody"

    tbody = tbody_match.group(1)
    rows = re.findall(
        r'<tr[^>]*id="a(\d+)"[^>]*gy="([^"]*)"[^>]*lid="(\d+)"[^>]*>(.*?)</tr>',
        tbody, re.DOTALL
    )

    matches = []
    for fid, gy, lid, row_html in rows:
        gy_parts = gy.split(',')
        league_raw = gy_parts[0].strip() if len(gy_parts) > 0 else ''

        if not is_football(league_raw):
            continue

        tds_raw = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)

        def strip_td(td_html):
            """解析td内容：去除HTML标签，用||分段"""
            s = re.sub(r'<[^>]+>', '||', td_html)
            s = re.sub(r'&nbsp;', '', s)
            s = re.sub(r'\s+', '', s)
            parts = [p.strip() for p in s.split('||') if p.strip()]
            return parts

        td_parts = [strip_td(td) for td in tds_raw]

        if len(td_parts) < 8:
            continue

        league = td_parts[0][0] if td_parts[0] else league_raw
        round_num = td_parts[1][0] if len(td_parts) > 1 and td_parts[1] else ''
        match_time = td_parts[2][0] if len(td_parts) > 2 and td_parts[2] else ''
        status = td_parts[3][0] if len(td_parts) > 3 and td_parts[3] else ''

        # td[4]: 主队 [rank, flag?, team_name]
        home_parts = td_parts[4] if len(td_parts) > 4 else []
        # td[5]: 比分盘口 [home_score, handicap/-, away_score]  格式: 2||一球||1
        score_parts = td_parts[5] if len(td_parts) > 5 else []
        # td[6]: 客队 [team_name, flag?, rank]
        away_parts = td_parts[6] if len(td_parts) > 6 else []
        # td[7]: 半场 [half_score]
        half_parts = td_parts[7] if len(td_parts) > 7 else []

        # 队名从gy取最准
        home = gy_parts[1].strip() if len(gy_parts) > 1 else (home_parts[-1] if home_parts else '')
        away = gy_parts[2].strip() if len(gy_parts) > 2 else (away_parts[0] if away_parts else '')

        # 比分: score_parts = [主得分, 盘口/- , 客得分]
        home_score = 0
        away_score = 0
        handicap = ''
        if len(score_parts) >= 3:
            try:
                home_score = int(score_parts[0])
            except ValueError:
                pass
            handicap = score_parts[1] if score_parts[1] != '-' else ''
            try:
                away_score = int(score_parts[2])
            except ValueError:
                pass
        elif len(score_parts) == 1:
            m = re.match(r'(\d+)\s*[-:]\s*(\d+)', score_parts[0])
            if m:
                home_score = int(m.group(1))
                away_score = int(m.group(2))

        # 半场
        half_home = half_away = 0
        half_str = half_parts[0] if half_parts else ''
        hm = re.match(r'(\d+)\s*[-:]\s*(\d+)', half_str)
        if hm:
            half_home = int(hm.group(1))
            half_away = int(hm.group(2))

        # 排名
        home_rank = ''
        away_rank = ''
        for p in home_parts:
            rm = re.match(r'\[(\d+)\]', p)
            if rm:
                home_rank = rm.group(1)
        for p in away_parts:
            rm = re.match(r'\[(\d+)\]', p)
            if rm:
                away_rank = rm.group(1)

        matches.append({
            'fid': int(fid),
            'date': date_str,
            'time': match_time,
            'league': league,
            'round': round_num,
            'home': home,
            'away': away,
            'home_score': home_score,
            'away_score': away_score,
            'half_home': half_home,
            'half_away': half_away,
            'handicap': handicap,
            'status': status,
            'lid': int(lid),
            'home_rank': home_rank,
            'away_rank': away_rank,
        })

    return matches, None


if __name__ == '__main__':
    existing = []
    existing_dates = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing_dates = {m['date'] for m in existing}
        print(f'已有 {len(existing)} 条, {len(existing_dates)} 天')

    start = datetime(2025, 1, 1)
    end = datetime(2026, 6, 12)

    total_dates = (end - start).days + 1
    done = 0
    errors = 0
    new_matches = []

    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')

        if date_str in existing_dates:
            current += timedelta(days=1)
            done += 1
            continue

        matches, err = scrape_date(date_str)

        if err:
            errors += 1
            print(f'{date_str}: 错误={err}')
        else:
            new_matches.extend(matches)
            if len(matches) > 0:
                print(f'{date_str}: {len(matches)} 场足球 ({done}/{total_dates})')

        done += 1
        current += timedelta(days=1)
        time.sleep(1.5)  # 避免被限速

    all_matches = existing + new_matches
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_matches, f, ensure_ascii=False)

    print(f'完成! 新增 {len(new_matches)} 场, 总计 {len(all_matches)} 场')
    print(f'出错 {errors} 天, 已有 {len(existing_dates)} 天')
