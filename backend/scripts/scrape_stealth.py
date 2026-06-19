"""
低调增量爬虫——慢速补全500.com历史数据
策略: 每次请求间隔3-8秒，每20天休息90秒
"""
import urllib.request, urllib.error, re, ssl, json, time, os, sys, random
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
OUTPUT_FILE = os.path.join(DATA_DIR, 'history_500.json')
PROGRESS_FILE = os.path.join(DATA_DIR, 'scrape_progress.txt')

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

COOKIE = 'ck_user2=bWhwNTc3ODEw; ck_user_utf8=mhp577810; token=MjAyNjA2MTIwMDAwNzk4NWUxNzM4MTk5YmFhODg2NzlmNTc4MWQxZTU0Y2UxYTk1; token_user=bWhwNTc3ODEw; usercheck=MjAyNjA2MTIwMDAwNzk4NTA5NmU0MDc2YzU0YTZmY2FlMmMxY2FmMzc3ZTI5MjQ1; isautologin=1; isagree=1'

UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
]


def strip_td(td_html):
    s = re.sub(r'<[^>]+>', '||', td_html)
    s = re.sub(r'&nbsp;', '', s)
    s = re.sub(r'\s+', '', s)
    return [p.strip() for p in s.split('||') if p.strip()]


def scrape_date(date_str):
    url = f'https://live.500.com/wanchang.php?e={date_str}'
    for attempt in range(3):
        try:
            hdrs = {
                'User-Agent': random.choice(UA_LIST),
                'Cookie': COOKIE,
                'Referer': 'https://live.500.com/',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as resp:
                html = resp.read().decode('gbk', errors='ignore')

            if '安全策略' in html or '567' in html:
                if attempt < 2:
                    time.sleep(10 + attempt * 5)
                    continue
                return [], 'WAF拦截'

            rows = re.findall(r'<tr\s+id=\"a(\d+)\"[^>]*gy=\"([^\"]*)\"[^>]*>(.*?)</tr>', html, re.DOTALL)
            matches = []
            for fid, gy, row_html in rows:
                gy_parts = gy.split(',')
                league = gy_parts[0].strip()
                home = gy_parts[1].strip() if len(gy_parts) > 1 else ''
                away = gy_parts[2].strip() if len(gy_parts) > 2 else ''

                tds_raw = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
                td_parts = [strip_td(td) for td in tds_raw]
                if len(td_parts) < 8:
                    continue

                status = td_parts[3][0] if td_parts[3] else ''
                score_parts = td_parts[5] if len(td_parts) > 5 else []
                half_parts = td_parts[7] if len(td_parts) > 7 else []

                hs = aws = 0
                handicap = ''
                if len(score_parts) >= 3:
                    try: hs = int(score_parts[0])
                    except: pass
                    handicap = score_parts[1] if score_parts[1] != '-' else ''
                    try: aws = int(score_parts[2])
                    except: pass

                half_h = half_a = 0
                if half_parts:
                    hm = re.match(r'(\d+)[-:](\d+)', half_parts[0])
                    if hm:
                        half_h, half_a = int(hm.group(1)), int(hm.group(2))

                matches.append({
                    'fid': int(fid), 'date': date_str, 'league': league,
                    'home': home, 'away': away,
                    'home_score': hs, 'away_score': aws,
                    'handicap': handicap, 'status': status,
                    'half_home': half_h, 'half_away': half_a,
                })
            return matches, None

        except urllib.error.HTTPError as e:
            if attempt < 2:
                time.sleep(5 + attempt * 3)
                continue
            return [], f'HTTP {e.code}'
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
                continue
            return [], str(e)


if __name__ == '__main__':
    # 加载已有数据
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding='utf-8') as f:
            all_data = json.load(f)
    else:
        all_data = []
    existing_dates = set(m['date'] for m in all_data if m.get('date'))

    # 加载进度
    done_dates = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            done_dates = set(line.strip() for line in f if line.strip())

    # 缺失日期
    start = datetime(2025, 1, 1)
    end = datetime(2026, 6, 12)
    missing = []
    d = start
    while d <= end:
        ds = d.strftime('%Y-%m-%d')
        if ds not in existing_dates and ds not in done_dates:
            missing.append(ds)
        d += timedelta(days=1)

    print(f'需爬取: {len(missing)} 天 (已有{len(existing_dates)}天, 已完成{len(done_dates)}天)')

    batch_size = 20
    total_added = 0
    errors_today = 0

    for i, date_str in enumerate(missing):
        # 每20天休息
        if i > 0 and i % batch_size == 0:
            rest = random.randint(60, 120)
            print(f'已爬 {i}/{len(missing)}, 休息 {rest}s...')
            time.sleep(rest)

        # 随机延时
        delay = random.uniform(4, 8)
        time.sleep(delay)

        matches, err = scrape_date(date_str)

        if err:
            errors_today += 1
            print(f'{date_str}: {err}')
            if errors_today > 5:
                print('连续错误过多, 暂停5分钟...')
                time.sleep(300)
                errors_today = 0
        else:
            errors_today = 0
            added = 0
            for m in matches:
                if not any(e.get('fid') == m['fid'] for e in all_data):
                    all_data.append(m)
                    added += 1
                    total_added += 1
            if len(matches) > 0:
                print(f'{date_str}: {len(matches)}场 (+{added}新) [{total_added}总计]')

            # 实时保存
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False)

        # 记录进度
        with open(PROGRESS_FILE, 'a') as f:
            f.write(date_str + '\n')

    print(f'完成! 新增 {total_added} 场, 总计 {len(all_data)} 场')
    # 自动关机
    import platform
    if platform.system() == 'Windows':
        os.system('shutdown /s /t 60')
        print('60秒后自动关机...')
    else:
        os.system('shutdown -h +1')
        print('1分钟后自动关机...')
