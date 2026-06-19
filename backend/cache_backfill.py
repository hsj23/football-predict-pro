"""一次性补全所有历史记录的detail_json缓存"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db_helper import db_connection
from datetime import datetime

conn = db_connection().__enter__()
cur = conn.cursor()

# 查所有没有缓存的记录
cur.execute("SELECT id, match_id, home_team, away_team, league FROM prediction_history WHERE detail_json IS NULL")
rows = cur.fetchall()
total = len(rows)
print(f'Need to backfill {total} records...')

if total == 0:
    print('All records already cached!')
    cur.close(); conn.close()
    sys.exit(0)

from services.prediction_service import PredictionService
predictor = PredictionService()

done = 0
for rid, mid, home, away, league in rows:
    try:
        print(f'  [{done+1}/{total}] {home} vs {away} ...', end=' ', flush=True)
        pred = predictor.generate_prediction(home, away, league, match_id=mid, historical=True)
        p = pred['prediction']

        dc = json.dumps({
            'probabilities': p.get('probabilities', {}),
            'odds_analysis': pred.get('odds_analysis', {}),
            'team_analysis': pred.get('team_analysis', {}),
            'h2h_analysis': pred.get('h2h_analysis', {}),
            'platform_predictions': pred.get('platform_predictions', []),
            'platform_votes': pred.get('platform_votes', {}),
            'analysis_summary': pred.get('analysis_summary', []),
            'news_analysis': pred.get('news_analysis', {}),
        }, ensure_ascii=False)

        cur.execute("UPDATE prediction_history SET detail_json=%s, confidence=%s, predicted_score=%s WHERE id=%s",
                    (dc, p['confidence'], p.get('predicted_score', ''), rid))
        conn.commit()
        done += 1
        print('OK')
    except Exception as e:
        print(f'FAIL: {e}')
        conn.rollback()

cur.close()
conn.close()
print(f'\nDone! Backfilled {done}/{total} records.')
