"""Test: fetch upcoming matches from sporttery API"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
from app.db_helper import db_cursor
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://m.sporttery.cn/mjc/jsq/zqspf/',
}

print("=" * 60)
print("Step 1: Fetching from sporttery API...")
API = 'https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry'
try:
    resp = requests.get(API, params={'channel': 'c'}, headers=HEADERS, timeout=15)
    print(f"   HTTP: {resp.status_code}")
    data = resp.json()
    match_list = data.get('value', {}).get('matchInfoList', [])
    print(f"   League groups: {len(match_list)}")

    total_matches = 0
    all_matches = []
    for info in match_list:
        bd = info.get('businessDate', '?')
        subs = info.get('subMatchList', [])
        print(f"   [{bd}] {info.get('leagueAllName', '?')}: {len(subs)} matches")
        for m in subs:
            home = m.get('homeTeamAllName', '')
            away = m.get('awayTeamAllName', '')
            md = m.get('matchDate', '')
            mt = m.get('matchTime', '')
            mn = m.get('matchNumStr', '')
            lg = m.get('leagueAllName', m.get('leagueName', ''))

            ho = do = ao = ''
            for pool in m.get('oddsList', []):
                if pool.get('poolCode') == 'HAD':
                    ho, do, ao = pool.get('h',''), pool.get('d',''), pool.get('a','')
                    break

            print(f"      #{mn} {home} vs {away} | {md} {mt} | {lg} | odds: {ho}/{do}/{ao}")
            all_matches.append({
                'match_id': f'JCZQ_{mn}',
                'home': home, 'away': away, 'league': lg,
                'match_time': f'{md} {mt}' if md else '',
                'ho': ho, 'do': do, 'ao': ao,
            })
            total_matches += 1

    print(f"\n   Total: {total_matches} matches")

    if total_matches == 0:
        print("\n   [FAIL] No matches from API")
        input("Press Enter...")
        sys.exit(1)

except Exception as e:
    print(f"   [FAIL] API error: {e}")
    import traceback
    traceback.print_exc()
    input("Press Enter...")
    sys.exit(1)

print("\nStep 2: Writing to database...")
try:
    with db_cursor() as cur:
        inserted = 0

        for m in all_matches:
            cur.execute('''INSERT INTO matches (match_id, league_name, home_team_name, away_team_name, match_time)
                VALUES (%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE league_name=VALUES(league_name), match_time=VALUES(match_time)''',
                (m['match_id'], m['league'], m['home'], m['away'], m['match_time']))
            inserted += 1

        if m['ho'] and m['do'] and m['ao']:
            cur.execute('''INSERT INTO odds (match_id, bookmaker, home_odds, draw_odds, away_odds, is_opening)
                VALUES (%s,%s,%s,%s,%s,0)
                ON DUPLICATE KEY UPDATE home_odds=VALUES(home_odds), draw_odds=VALUES(draw_odds), away_odds=VALUES(away_odds)''',
                (m['match_id'], 'sporttery_cn', m['ho'], m['do'], m['ao']))

    conn.commit()

    # Verify
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM matches WHERE match_time >= %s", (today,))
    count = cur.fetchone()[0]
    print(f"   Inserted: {inserted} matches")
    print(f"   DB total (from today): {count} matches")

    cur.execute("SELECT match_id, league_name, home_team_name, away_team_name, match_time FROM matches WHERE match_time >= %s ORDER BY match_time LIMIT 10", (today,))
    rows = cur.fetchall()
    print(f"\n   Matches in DB:")
    for r in rows:
        print(f"     {r[0]} | {r[1]} | {r[2]} vs {r[3]} | {r[4]}")

    print("\n   [OK] Data written to database!")
except Exception as e:
    print(f"   [FAIL] DB error: {e}")
    import traceback
    traceback.print_exc()
    input("Press Enter...")
    sys.exit(1)

print("\n" + "=" * 60)
print("DONE! Refresh http://127.0.0.1:8000 to see new matches.")
print("=" * 60)
