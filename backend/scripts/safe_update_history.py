"""
安全更新历史预测 — 只改错的，不改对的
"""
import sys
sys.path.insert(0, 'D:/小黄的助手/足彩预测系统/backend')
from app.db_helper import db_cursor
from ml.hybrid_predictor import HybridPredictor
from datetime import datetime

hp = HybridPredictor()

# 1. 获取所有有实际结果的记录
with db_cursor() as cur:
    cur.execute('''
        SELECT match_id, home_team, away_team, league, 
               prediction_result, confidence, predicted_score, actual_result
        FROM prediction_history 
        WHERE actual_result IS NOT NULL AND actual_result != ''
        ORDER BY match_date DESC
    ''')
    rows = cur.fetchall()

print(f'总历史记录: {len(rows)} 条')
print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print()

# 2. 统计当前准确率
old_correct = sum(1 for r in rows if r[4] == r[7])
old_total = len(rows)
old_acc = old_correct / old_total * 100 if old_total > 0 else 0
print(f'当前准确率: {old_correct}/{old_total} = {old_acc:.1f}%')
print()

# 3. 逐条分析
updated = 0
skipped_better = 0
skipped_same = 0
improved = 0
worsened = 0

print('=' * 70)
print('逐条分析:')
print('=' * 70)

for r in rows:
    match_id, home, away, league, old_pred, old_conf, old_score, actual = r
    old_correct_flag = (old_pred == actual)

    try:
        result = hp.predict(home, away, league)
        new_pred = result['prediction']
        new_conf = result['confidence']
        new_score = result.get('predicted_score', '')
    except Exception as e:
        print(f'  跳过 {home} vs {away}: {e}')
        continue

    new_correct_flag = (new_pred == actual)

    # 安全策略：只更新"旧错新对"的情况
    if old_correct_flag and not new_correct_flag:
        # 旧对新错 → 不更新
        print(f'  保护: {home} vs {away} | 旧:{old_pred}(对) 新:{new_pred}(错) → 保留旧')
        skipped_better += 1
    elif not old_correct_flag and new_correct_flag:
        # 旧错新对 → 更新
        print(f'  更新: {home} vs {away} | 旧:{old_pred}(错) 新:{new_pred}(对) → 更新')
        with db_cursor() as cur2:
            pred_name = {'home': '主胜', 'draw': '平局', 'away': '客胜'}[new_pred]
            cur2.execute('''
                UPDATE prediction_history 
                SET prediction_result=%s, prediction_name=%s, confidence=%s, predicted_score=%s
                WHERE match_id=%s
            ''', (new_pred, pred_name, new_conf, new_score, match_id))
        updated += 1
        improved += 1
    elif not old_correct_flag and not new_correct_flag:
        # 都错 → 保留置信度更高的
        if new_conf > old_conf:
            print(f'  升级: {home} vs {away} | 旧:{old_pred}({old_conf}%) 新:{new_pred}({new_conf}%) → 更新置信度')
            with db_cursor() as cur2:
                pred_name = {'home': '主胜', 'draw': '平局', 'away': '客胜'}[new_pred]
                cur2.execute('''
                    UPDATE prediction_history 
                    SET prediction_result=%s, prediction_name=%s, confidence=%s, predicted_score=%s
                    WHERE match_id=%s
                ''', (new_pred, pred_name, new_conf, new_score, match_id))
            updated += 1
        else:
            skipped_same += 1
    else:
        # 都对 → 不更新
        skipped_same += 1

# 4. 统计更新后准确率
with db_cursor() as cur:
    cur.execute('''
        SELECT prediction_result, actual_result FROM prediction_history 
        WHERE actual_result IS NOT NULL AND actual_result != ''
    ''')
    new_rows = cur.fetchall()

new_correct = sum(1 for r in new_rows if r[0] == r[1])
new_total = len(new_rows)
new_acc = new_correct / new_total * 100 if new_total > 0 else 0

print()
print('=' * 70)
print('汇总报告:')
print('=' * 70)
print(f'总记录: {old_total} 条')
print(f'更新: {updated} 条 (其中 {improved} 条从错→对)')
print(f'保护: {skipped_better} 条 (旧对新错，保留旧)')
print(f'不变: {skipped_same} 条')
print()
print(f'准确率: {old_acc:.1f}% → {new_acc:.1f}% ({old_correct}→{new_correct}/{new_total})')
if new_acc > old_acc:
    print(f'提升: +{new_acc - old_acc:.1f}%')
elif new_acc < old_acc:
    print(f'下降: {new_acc - old_acc:.1f}% (有保护机制，不应发生)')
else:
    print('无变化')
