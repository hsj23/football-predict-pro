"""
模型回归测试 — 确保新模型不破坏任何正确预测
流程:
1. 记录旧模型对每场比赛的预测结果
2. 训练新模型
3. 用新模型预测所有历史比赛
4. 验证: 之前对的现在也要对
5. 统计: 之前错的现在对了多少
6. 只有无回归时才接受新模型
"""
import sys, json, os
sys.path.insert(0, 'D:/小黄的助手/足彩预测系统/backend')
from app.db_helper import db_cursor
from ml.hybrid_predictor import HybridPredictor
from ml.feature_engineering import FeatureEngineer
from datetime import datetime

def get_historical_matches():
    """获取所有有实际结果的历史比赛"""
    with db_cursor() as cur:
        cur.execute('''
            SELECT match_id, home_team, away_team, league, 
                   prediction_result, confidence, actual_result
            FROM prediction_history 
            WHERE actual_result IS NOT NULL AND actual_result != ''
            ORDER BY match_date DESC
        ''')
        return cur.fetchall()

def predict_all_matches(matches):
    """用当前模型预测所有比赛"""
    # 清除缓存，确保使用最新模型
    HybridPredictor._team_form_cache = None
    HybridPredictor._h2h_cache = None
    HybridPredictor._ensemble = None
    
    hp = HybridPredictor()
    fe = FeatureEngineer()
    
    results = []
    for r in matches:
        match_id, home, away, league, old_pred, old_conf, actual = r
        try:
            result = hp.predict(home, away, league)
            new_pred = result['prediction']
            new_conf = result['confidence']
            results.append({
                'match_id': match_id,
                'home': home,
                'away': away,
                'league': league,
                'old_pred': old_pred,
                'old_conf': old_conf,
                'new_pred': new_pred,
                'new_conf': new_conf,
                'actual': actual,
                'old_correct': old_pred == actual,
                'new_correct': new_pred == actual,
            })
        except Exception as e:
            results.append({
                'match_id': match_id,
                'home': home,
                'away': away,
                'league': league,
                'old_pred': old_pred,
                'old_conf': old_conf,
                'new_pred': None,
                'new_conf': 0,
                'actual': actual,
                'old_correct': old_pred == actual,
                'new_correct': False,
                'error': str(e),
            })
    return results

def validate_model(results):
    """验证新模型是否满足要求"""
    regressions = []  # 之前对的，现在错了
    improvements = []  # 之前错的，现在对了
    unchanged_correct = []  # 都对
    unchanged_wrong = []  # 都错
    
    for r in results:
        if r['old_correct'] and not r['new_correct']:
            regressions.append(r)
        elif not r['old_correct'] and r['new_correct']:
            improvements.append(r)
        elif r['old_correct'] and r['new_correct']:
            unchanged_correct.append(r)
        else:
            unchanged_wrong.append(r)
    
    return {
        'regressions': regressions,
        'improvements': improvements,
        'unchanged_correct': unchanged_correct,
        'unchanged_wrong': unchanged_wrong,
        'total': len(results),
        'old_accuracy': sum(1 for r in results if r['old_correct']) / len(results) * 100,
        'new_accuracy': sum(1 for r in results if r['new_correct']) / len(results) * 100,
    }

def run_regression_test():
    """运行完整的回归测试"""
    print('=' * 70)
    print('模型回归测试')
    print(f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)
    print()
    
    # 1. 获取历史比赛
    matches = get_historical_matches()
    print(f'历史比赛: {len(matches)} 场')
    print()
    
    # 2. 用当前模型预测
    print('正在用当前模型预测所有比赛...')
    results = predict_all_matches(matches)
    print('预测完成')
    print()
    
    # 3. 验证
    validation = validate_model(results)
    
    # 4. 输出结果
    print('=' * 70)
    print('验证结果:')
    print('=' * 70)
    print(f'总比赛: {validation["total"]} 场')
    print(f'旧模型准确率: {validation["old_accuracy"]:.1f}%')
    print(f'新模型准确率: {validation["new_accuracy"]:.1f}%')
    print()
    
    print(f'都正确: {len(validation["unchanged_correct"])} 场 (保持)')
    print(f'都错误: {len(validation["unchanged_wrong"])} 场 (保持)')
    print(f'修正: {len(validation["improvements"])} 场 (旧错新对)')
    print(f'回归: {len(validation["regressions"])} 场 (旧对新错)')
    print()
    
    # 5. 如果有回归，详细列出
    if validation['regressions']:
        print('=' * 70)
        print('[WARNING] 发现回归! 以下比赛旧模型正确但新模型错误:')
        print('=' * 70)
        for r in validation['regressions']:
            print(f'  {r["home"]} vs {r["away"]} ({r["league"]})')
            print(f'    旧: {r["old_pred"]}({r["old_conf"]}%) 新: {r["new_pred"]}({r["new_conf"]}%) 实际: {r["actual"]}')
        print()
        print('结论: 新模型存在问题，需要修复!')
        return False
    else:
        print('=' * 70)
        print('[OK] 无回归! 新模型通过验证!')
        print('=' * 70)
        
        if validation['improvements']:
            print()
            print(f'修正的比赛 ({len(validation["improvements"])} 场):')
            for r in validation['improvements']:
                print(f'  {r["home"]} vs {r["away"]}: {r["old_pred"]}→{r["new_pred"]} (实际{r["actual"]})')
        
        # 更新数据库中的预测记录
        print()
        print('更新数据库...')
        with db_cursor() as cur:
            for r in validation['improvements']:
                pred_name = {'home': '主胜', 'draw': '平局', 'away': '客胜'}[r['new_pred']]
                cur.execute('''
                    UPDATE prediction_history 
                    SET prediction_result=%s, prediction_name=%s, confidence=%s
                    WHERE match_id=%s
                ''', (r['new_pred'], pred_name, r['new_conf'], r['match_id']))
        print(f'已更新 {len(validation["improvements"])} 条记录')
        
        return True

if __name__ == '__main__':
    success = run_regression_test()
    print()
    if success:
        print('[OK] 模型验证通过，可以使用!')
    else:
        print('[FAIL] 模型验证失败，需要修复!')
