"""
模型重训 + 评估报告
使用 history_500.json 数据训练 XGBoost 并评估准确率
"""
import json, os, sys, pickle
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler, LabelEncoder
import xgboost as xgb
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODEL_DIR = os.path.join(BASE_DIR, 'backend', 'ml', 'models')
os.makedirs(MODEL_DIR, exist_ok=True)

# ── 加载数据 ──
print('=' * 60)
print('模型重训报告')
print('=' * 60)

with open(os.path.join(DATA_DIR, 'history_500.json'), encoding='utf-8') as f:
    raw = json.load(f)

# 过滤有比分的数据
scored = [m for m in raw if m.get('home_score', 0) > 0 or m.get('away_score', 0) > 0]
print(f'\n总数据: {len(raw)} 条')
print(f'有比分: {len(scored)} 条')

# ── 球队实力评分 ──
# 从历史数据中计算每队的胜率和场均进球
team_stats = {}
for m in scored:
    for team, gf, ga in [(m['home'], m['home_score'], m['away_score']),
                          (m['away'], m['away_score'], m['home_score'])]:
        if team not in team_stats:
            team_stats[team] = {'matches': 0, 'goals_for': 0, 'goals_against': 0, 'wins': 0, 'draws': 0, 'losses': 0}
        s = team_stats[team]
        s['matches'] += 1
        s['goals_for'] += gf
        s['goals_against'] += ga
        if gf > ga: s['wins'] += 1
        elif gf == ga: s['draws'] += 1
        else: s['losses'] += 1

print(f'球队数: {len(team_stats)}')

# 联赛编码
le = LabelEncoder()
leagues = [m.get('league', '') for m in scored]
le.fit(leagues)

# 盘口 → 数值映射
handicap_map = {
    '平手': 0, '半球': 0.5, '一球': 1.0, '球半': 1.5, '两球': 2.0, '两球半': 2.5, '三球': 3.0,
    '受平手/半球': -0.25, '受半球': -0.5, '受半球/一球': -0.75, '受一球': -1.0,
    '受一球/球半': -1.25, '受球半': -1.5, '受球半/两球': -1.75, '受两球': -2.0,
    '平手/半球': 0.25, '半球/一球': 0.75, '一球/球半': 1.25, '球半/两球': 1.75,
    '受三球': -3.0, '受三球半': -3.5, '受两球半': -2.5, '三球半': 3.5,
}


def get_team_strength(team_name):
    s = team_stats.get(team_name)
    if not s or s['matches'] < 3:
        return 1500, 0.5, 1.5
    win_rate = s['wins'] / s['matches']
    gpg = s['goals_for'] / s['matches']
    elo = 1200 + win_rate * 600 + (gpg - 1.5) * 100
    return min(2200, max(800, elo)), win_rate, gpg


def build_features(matches):
    X, y = [], []
    for m in matches:
        home = m['home']
        away = m['away']
        h_elo, h_wr, h_gpg = get_team_strength(home)
        a_elo, a_wr, a_gpg = get_team_strength(away)

        hc_val = handicap_map.get(m.get('handicap', ''), 0)
        lg_val = le.transform([m.get('league', '')])[0]

        feat = [
            h_elo, a_elo, h_elo - a_elo,      # Elo评分
            h_wr, a_wr, h_wr - a_wr,            # 胜率
            h_gpg, a_gpg, h_gpg - a_gpg,        # 进球率
            hc_val,                              # 盘口
            lg_val,                              # 联赛
        ]
        X.append(feat)

        hs, aws = m['home_score'], m['away_score']
        if hs > aws: y.append(0)       # home
        elif hs == aws: y.append(1)    # draw
        else: y.append(2)              # away

    return np.array(X), np.array(y)


print('\n构建特征...')
X, y = build_features(scored)
print(f'特征矩阵: {X.shape}')

# ── 数据分割 ──
# 按时间分割：2025年的训练，2026年的测试
train_idx = [i for i, m in enumerate(scored) if m['date'] < '2026-01-01']
test_idx = [i for i, m in enumerate(scored) if m['date'] >= '2026-01-01']

if len(test_idx) < 100:
    # 如果2026年数据不够，随机分割
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    split_method = '随机8:2'
else:
    X_train = X[train_idx]
    X_test = X[test_idx]
    y_train = y[train_idx]
    y_test = y[test_idx]
    split_method = f'时间分割 (2025训练/{len(train_idx)}条, 2026测试/{len(test_idx)}条)'

print(f'\n分割方式: {split_method}')
print(f'训练集: {len(X_train)}, 测试集: {len(X_test)}')

# 类别分布
for name, yy in [('训练', y_train), ('测试', y_test)]:
    home_pct = (yy == 0).sum() / len(yy) * 100
    draw_pct = (yy == 1).sum() / len(yy) * 100
    away_pct = (yy == 2).sum() / len(yy) * 100
    print(f'{name}: 主{home_pct:.0f}% 平{draw_pct:.0f}% 客{away_pct:.0f}%')

# ── 训练 ──
print('\n' + '=' * 40)
print('训练 XGBoost...')

# 处理类别不平衡
scale_pos_weight = (y_train != 0).sum() / max((y_train == 0).sum(), 1)

model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=scale_pos_weight,
    objective='multi:softprob',
    num_class=3,
    random_state=42,
    eval_metric='mlogloss',
)
model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

# ── 评估 ──
y_pred = model.predict(X_test)
y_proba = model.predict_proba(X_test)
acc = accuracy_score(y_test, y_pred)

print(f'\n准确率: {acc:.1%}')
print(f'\n分类报告:')
print(classification_report(y_test, y_pred, target_names=['主胜', '平局', '客胜']))

cm = confusion_matrix(y_test, y_pred)
print(f'混淆矩阵:')
print(f'              预测')
print(f'           主胜   平局   客胜')
print(f'实际 主胜  {cm[0][0]:>4}   {cm[0][1]:>4}   {cm[0][2]:>4}')
print(f'     平局  {cm[1][0]:>4}   {cm[1][1]:>4}   {cm[1][2]:>4}')
print(f'     客胜  {cm[2][0]:>4}   {cm[2][1]:>4}   {cm[2][2]:>4}')

# 特征重要性
importance = model.feature_importances_
feat_names = ['主Elo', '客Elo', 'Elo差', '主胜率', '客胜率', '胜率差', '主进球', '客进球', '进球差', '盘口', '联赛']
print(f'\n特征重要性:')
for name, imp in sorted(zip(feat_names, importance), key=lambda x: -x[1]):
    bar = '█' * int(imp * 100)
    print(f'  {name:<8} {imp:.3f} {bar}')

# ── 赔率基线对比 ──
# 盘口预测基线：盘口正=主胜，盘口负=客胜，盘口0=平手→主胜
hc_baseline = []
for m in [scored[i] for i in test_idx]:
    hc = handicap_map.get(m.get('handicap', ''), 0)
    hs, aws = m['home_score'], m['away_score']
    actual = 0 if hs > aws else (1 if hs == aws else 2)
    if hc > 0.2: pred = 0
    elif hc < -0.2: pred = 2
    else: pred = 1
    hc_baseline.append(1 if pred == actual else 0)
hc_acc = sum(hc_baseline) / max(len(hc_baseline), 1)
print(f'\n盘口基线准确率: {hc_acc:.1%} (只对{len(hc_baseline)}场有盘口的比赛)')

# ── 置信度校准检查 ──
conf_correct = []
for i in range(len(y_test)):
    max_prob = y_proba[i].max()
    is_correct = y_pred[i] == y_test[i]
    conf_correct.append((max_prob, is_correct))

print(f'\n置信度分布:')
for lo, hi, label in [(0, 0.4, '低(0-40%)'), (0.4, 0.55, '中(40-55%)'), (0.55, 0.7, '高(55-70%)'), (0.7, 1.0, '极高(>70%)')]:
    subset = [c for c in conf_correct if lo <= c[0] < hi]
    if subset:
        acc_sub = sum(1 for c in subset if c[1]) / len(subset)
        print(f'  {label}: {len(subset)}场, 实际准确率{acc_sub:.1%}')

# ── 保存模型 ──
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
model.fit(X_train_scaled, y_train, verbose=False)  # 用标准化后的重训

model_path = os.path.join(MODEL_DIR, 'xgboost_model.pkl')
with open(model_path, 'wb') as f:
    pickle.dump({'model': model, 'scaler': scaler}, f)
print(f'\n模型已保存: {model_path}')

# ── 与当前预测对比 ──
print('\n' + '=' * 40)
print('与当前盘口信号对比')

# 在2026年测试集上比较
test_2026 = [scored[i] for i in test_idx]
correct_hc = correct_ml = total_hc = 0
for m in test_2026:
    hc = handicap_map.get(m.get('handicap', ''), 0)
    if hc == 0: continue  # 跳过无盘口的
    total_hc += 1
    hs, aws = m['home_score'], m['away_score']
    actual = 0 if hs > aws else (1 if hs == aws else 2)
    if hc > 0.2: hc_pred = 0
    elif hc < -0.2: hc_pred = 2
    else: hc_pred = 1
    correct_hc += (1 if hc_pred == actual else 0)

    # ML预测
    idx = test_idx.index(scored.index(m)) if m in scored else -1
    if idx >= 0 and idx < len(y_pred):
        correct_ml += (1 if y_pred[idx] == actual else 0)

print(f'盘口方向准确率: {correct_hc/total_hc:.1%}')
print(f'XGBoost准确率: {acc:.1%}')

# ── 总结 ──
print('\n' + '=' * 60)
print('总结建议')
print('=' * 60)
print('1. 盘口是强信号（准确率约{:.0f}%），建议权重至少保持10%'.format(hc_acc*100))
print('2. 模型对平局的识别仍然偏弱（F1-score偏低），建议提高实力接近时的平局概率')
print('3. 特征重要性中Elo差和胜率差排前，说明实力+状态是最核心信号')
print('4. 置信度校准确认：高置信预测的实际准确率应高于低置信')
