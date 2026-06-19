import sys
sys.path.insert(0, 'backend')

from ml.feature_engineering import FeatureEngineer

fe = FeatureEngineer()
print(f'特征数量: {len(fe.FEATURE_NAMES)}')

# 测试伊拉克 vs 挪威 (世界杯 - 中立场地)
match_data = {'home_team_name': '伊拉克', 'away_team_name': '挪威', 'league_name': '世界杯'}
odds_data = {'odds': ['2.5', '3.2', '2.8']}

features = fe.extract_features(match_data, odds_data)
print(f'\n=== 伊拉克 vs 挪威 (世界杯) ===')
print(f'主场优势: {features[28]}')
print(f'中立场地: {features[29]}')
print(f'实力差异: {features[30]:.4f}')
print(f'主胜概率: {features[0]:.4f}')
print(f'平局概率: {features[1]:.4f}')
print(f'客胜概率: {features[2]:.4f}')

# 测试英超比赛 (正常主场)
match_data2 = {'home_team_name': '曼城', 'away_team_name': '利物浦', 'league_name': '英超'}
odds_data2 = {'odds': ['1.85', '3.50', '4.20']}

features2 = fe.extract_features(match_data2, odds_data2)
print(f'\n=== 曼城 vs 利物浦 (英超) ===')
print(f'主场优势: {features2[28]}')
print(f'中立场地: {features2[29]}')
print(f'实力差异: {features2[30]:.4f}')
print(f'主胜概率: {features2[0]:.4f}')
print(f'平局概率: {features2[1]:.4f}')
print(f'客胜概率: {features2[2]:.4f}')
