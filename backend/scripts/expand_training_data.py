"""
扩充训练数据集 — 从体彩官方API获取历史比赛（含赔率），合并并重训ML模型
"""
import sys, os, json, time, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.sporttery_scraper import fetch_all_results

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')


def expand_from_sporttery():
    """从体彩API获取历史数据(2025-11 ~ 2026-06)，含真实SP赔率"""
    months = [
        ('2025-11-01', '2025-11-30'),
        ('2025-12-01', '2025-12-31'),
        ('2026-01-01', '2026-01-31'),
        ('2026-02-01', '2026-02-28'),
        ('2026-03-01', '2026-03-31'),
        ('2026-04-01', '2026-04-30'),
        ('2026-05-01', '2026-05-31'),
        ('2026-06-01', '2026-06-30'),
    ]

    all_matches = []
    for begin, end in months:
        logger.info(f"获取 {begin} ~ {end}...")
        matches = fetch_all_results(begin, end)
        logger.info(f"  → {len(matches)} 场")
        all_matches.extend(matches)
        time.sleep(0.5)

    # 去重
    seen = set()
    unique = []
    for m in all_matches:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    with_odds = sum(1 for m in unique if m.get('odds') and len(m['odds']) == 3)
    logger.info(f"总计: {len(unique)} 场, 含赔率: {with_odds} 场")

    # 按联赛统计
    leagues = {}
    for m in unique:
        lg = m.get('league', '未知')
        leagues[lg] = leagues.get(lg, 0) + 1
    for lg, cnt in sorted(leagues.items(), key=lambda x: -x[1])[:20]:
        logger.info(f"  {lg}: {cnt}")

    return unique


def merge_to_training_data(new_matches):
    """合并到 training_data.json，去重"""
    train_file = os.path.join(DATA_DIR, 'training_data.json')
    existing = []
    if os.path.exists(train_file):
        with open(train_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing_keys = {f"{m.get('home','')}_{m.get('away','')}_{m.get('date','')}" for m in existing}

    # 统计现有数据中有赔率的比例
    existing_with_odds = sum(1 for m in existing if m.get('odds') and len(m.get('odds', [])) == 3)
    logger.info(f"现有训练数据: {len(existing)} 场, 含赔率: {existing_with_odds} 场 ({existing_with_odds/len(existing)*100:.1f}%)")

    added = 0
    for m in new_matches:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in existing_keys:
            # 补充 home_score/away_score
            score = m.get('full_score', '')
            if ':' in score:
                parts = score.split(':')
                m['home_score'] = int(parts[0])
                m['away_score'] = int(parts[1])
            existing.append(m)
            existing_keys.add(key)
            added += 1

    if added > 0:
        with open(train_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"新增 {added} 场, 总计 {len(existing)} 场")

    # 重新统计
    new_with_odds = sum(1 for m in existing if m.get('odds') and len(m.get('odds', [])) == 3)
    logger.info(f"合并后: {len(existing)} 场, 含赔率: {new_with_odds} 场 ({new_with_odds/len(existing)*100:.1f}%)")

    return existing


def retrain_model():
    """用扩展数据重训 ML 模型"""
    logger.info("=" * 50)
    logger.info("开始重训模型...")
    from ml.model_trainer import ModelTrainer

    trainer = ModelTrainer()
    data_path = os.path.join(DATA_DIR, 'training_data.json')

    try:
        metrics = trainer.train(data_path)
        logger.info(f"训练完成: {metrics}")
    except Exception as e:
        logger.error(f"训练失败: {e}")
        return False

    # 保存模型
    model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ml', 'models')
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, 'xgboost_model.pkl')
    trainer.save_model(model_path)
    logger.info(f"模型已保存: {model_path}")
    return True


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("训练数据扩充 + 模型重训")
    logger.info("=" * 60)

    # Step 1: 从体彩API获取数据
    logger.info("\n[1/3] 从体彩API获取历史数据...")
    new_matches = expand_from_sporttery()

    # Step 2: 合并到训练数据
    logger.info("\n[2/3] 合并到训练数据...")
    merge_to_training_data(new_matches)

    # Step 3: 重训模型
    logger.info("\n[3/3] 重训ML模型...")
    retrain_model()

    logger.info("\n完成！")
