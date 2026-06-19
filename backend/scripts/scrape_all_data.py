"""
多源数据采集器 — football-data.co.uk CSV + 体彩API + 自动重训
"""
import os, sys, csv, json, time, logging
from io import StringIO
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')
TRAINING_FILE = os.path.join(DATA_DIR, 'training_data.json')

# ── football-data.co.uk 联赛代码 ──
# 格式: (联赛代码, 中文名, 赛季列表)
FD_LEAGUES = [
    ('E0', '英超', ['2021', '2122', '2223', '2324', '2425']),
    ('D1', '德甲', ['2122', '2223', '2324', '2425']),
    ('D2', '德乙', ['2223', '2324', '2425']),
    ('I1', '意甲', ['2122', '2223', '2324', '2425']),
    ('SP1', '西甲', ['2122', '2223', '2324', '2425']),
    ('F1', '法甲', ['2122', '2223', '2324', '2425']),
    ('P1', '葡超', ['2223', '2324', '2425']),
    ('N1', '荷甲', ['2223', '2324', '2425']),
    ('B1', '比甲', ['2223', '2324', '2425']),
    ('T1', '土超', ['2223', '2324', '2425']),
    ('G1', '希超', ['2223', '2324', '2425']),
    ('SC0', '苏超', ['2223', '2324', '2425']),
]

FD_BASE = 'https://www.football-data.co.uk/mmz4281'

# ── 中文队名映射（英文 → 中文，从现有数据学习） ──
TEAM_NAME_MAP = {}


def load_existing_names():
    """从现有训练数据加载英文→中文队名映射"""
    global TEAM_NAME_MAP
    if TEAM_NAME_MAP:
        return
    if os.path.exists(TRAINING_FILE):
        with open(TRAINING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for m in data:
            home_en = m.get('home_en', '').strip()
            home_cn = m.get('home', '').strip()
            away_en = m.get('away_en', '').strip()
            away_cn = m.get('away', '').strip()
            if home_en and home_cn and home_en not in TEAM_NAME_MAP:
                TEAM_NAME_MAP[home_en] = home_cn
            if away_en and away_cn and away_en not in TEAM_NAME_MAP:
                TEAM_NAME_MAP[away_en] = away_cn
    logger.info(f"已有 {len(TEAM_NAME_MAP)} 个队名映射")


def translate_name(en_name: str) -> str:
    """英文队名翻译为中文（映射表 + 拼音规则兜底）"""
    if en_name in TEAM_NAME_MAP:
        return TEAM_NAME_MAP[en_name]
    # 返回英文名（兜底）
    return en_name


def fetch_fd_csv(league_code: str, season: str) -> list:
    """下载 football-data.co.uk 的 CSV 数据"""
    url = f'{FD_BASE}/{season}/{league_code}.csv'
    try:
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; FootballPredict/1.0)'
        })
        if resp.status_code == 200:
            reader = csv.DictReader(StringIO(resp.text))
            return list(reader)
        else:
            logger.warning(f"  {league_code} {season}: HTTP {resp.status_code}")
            return []
    except Exception as e:
        logger.warning(f"  {league_code} {season}: {e}")
        return []


def parse_fd_match(row: dict, league_cn: str, season: str) -> dict:
    """将 football-data CSV 行转为训练数据格式"""
    home = row.get('HomeTeam', '').strip()
    away = row.get('AwayTeam', '').strip()
    fthg = row.get('FTHG', '')
    ftag = row.get('FTAG', '')
    date_str = row.get('Date', '')

    if not home or not away or not fthg or not ftag:
        return None

    try:
        hs = int(fthg)
        ags = int(ftag)
    except ValueError:
        return None

    # 解析日期 (DD/MM/YYYY 或 DD/MM/YY)
    try:
        parts = date_str.split('/')
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            date = f'{y:04d}-{m:02d}-{d:02d}'
        else:
            date = date_str
    except Exception:
        date = date_str

    # 赔率 (Bet365 是最常用的参考)
    odds = None
    try:
        b365h = row.get('B365H', '')
        b365d = row.get('B365D', '')
        b365a = row.get('B365A', '')
        if b365h and b365d and b365a:
            odds = [float(b365h), float(b365d), float(b365a)]
    except (ValueError, TypeError):
        pass

    # 如果没有 B365，尝试其他博彩公司
    if odds is None:
        for prefix in ['WH', 'VC', 'IW', 'PS']:
            try:
                h = row.get(f'{prefix}H', '')
                d = row.get(f'{prefix}D', '')
                a = row.get(f'{prefix}A', '')
                if h and d and a:
                    odds = [float(h), float(d), float(a)]
                    break
            except (ValueError, TypeError):
                continue

    home_cn = translate_name(home)
    away_cn = translate_name(away)

    return {
        'home': home_cn,
        'away': away_cn,
        'home_en': home,
        'away_en': away,
        'league': league_cn,
        'full_score': f'{hs}:{ags}',
        'home_score': hs,
        'away_score': ags,
        'date': date,
        'odds': odds,
        'source': f'football_data_{league_cn}_{season}',
    }


def scrape_football_data() -> list:
    """主函数：采集 football-data.co.uk 数据"""
    load_existing_names()
    all_matches = []

    for code, league_cn, seasons in FD_LEAGUES:
        for season in seasons:
            logger.info(f"获取 {league_cn}({code}) {season}...")
            rows = fetch_fd_csv(code, season)
            for row in rows:
                match = parse_fd_match(row, league_cn, season)
                if match and match['date']:
                    all_matches.append(match)
            logger.info(f"  → {len(rows)} 行")
            time.sleep(0.5)  # 控制频率

    # 去重
    seen = set()
    unique = []
    for m in all_matches:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)

    with_odds = sum(1 for m in unique if m.get('odds') and len(m['odds']) == 3)
    logger.info(f"football-data: {len(unique)} 场, 含赔率 {with_odds} 场")

    return unique


def merge_all_data():
    """合并所有数据源到 training_data.json"""
    os.makedirs(DATA_DIR, exist_ok=True)

    existing = []
    if os.path.exists(TRAINING_FILE):
        with open(TRAINING_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    existing_keys = {f"{m.get('home','')}_{m.get('away','')}_{m.get('date','')}" for m in existing}
    logger.info(f"现有数据: {len(existing)} 场")

    # 1) football-data.co.uk
    fd_matches = scrape_football_data()
    added_fd = 0
    for m in fd_matches:
        key = f"{m['home']}_{m['away']}_{m['date']}"
        if key not in existing_keys:
            existing.append(m)
            existing_keys.add(key)
            added_fd += 1
    logger.info(f"football-data 新增: {added_fd} 场")

    # 2) 体彩 API 2025数据（如果之前没采集完整）
    try:
        from crawlers.sporttery_scraper import fetch_all_results
        api_matches = fetch_all_results('2025-11-01', '2026-06-30')
        added_api = 0
        for m in api_matches:
            key = f"{m['home']}_{m['away']}_{m['date']}"
            if key not in existing_keys:
                if ':' in m.get('full_score', ''):
                    parts = m['full_score'].split(':')
                    m['home_score'] = int(parts[0])
                    m['away_score'] = int(parts[1])
                existing.append(m)
                existing_keys.add(key)
                added_api += 1
        logger.info(f"体彩API 新增: {added_api} 场")
    except Exception as e:
        logger.warning(f"体彩API采集失败: {e}")

    # 保存
    with open(TRAINING_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    with_odds = sum(1 for m in existing if m.get('odds') and len(m.get('odds', [])) == 3)
    logger.info(f"合并后总计: {len(existing)} 场, 含赔率: {with_odds} 场 ({with_odds/len(existing)*100:.1f}%)")

    return existing


def retrain_all():
    """重训所有模型"""
    logger.info("=" * 50)
    logger.info("重训 Dixon-Coles + Ensemble...")

    # Dixon-Coles
    from ml.dixon_coles import DixonColesModel
    dc = DixonColesModel()

    # Ensemble
    from ml.ensemble_trainer import EnsemblePredictor
    ep = EnsemblePredictor()
    results = ep.train_and_save()
    if results:
        logger.info(f"Ensemble: {results['accuracy_pct']}, per_class: {results['per_class_accuracy']}")

    # 同时更新 XGBoost
    from ml.model_trainer import ModelTrainer
    trainer = ModelTrainer()
    xgb_results = trainer.train()
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'ml', 'models', 'xgboost_model.pkl')
    trainer.save_model(model_path)
    if xgb_results:
        logger.info(f"XGBoost: {xgb_results.get('accuracy_pct', '?')}")

    return True


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("多源数据采集 + 模型重训")
    logger.info("=" * 60)
    merge_all_data()
    retrain_all()
    logger.info("全部完成！")
