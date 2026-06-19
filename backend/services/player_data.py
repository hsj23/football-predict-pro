"""
球员身价/数据 + 教练数据 作为预测参考
数据源: data/players.json, data/coaches.json
"""
import os, json, logging

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')

_cache = {}
_cache_time = 0


def _load_json(name):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_team_player_value(team_name: str) -> dict:
    """
    返回队伍球员数据汇总:
    {total_value_m, avg_value_m, top_scorer: {name, goals}, key_missing: [...]}
    """
    global _cache, _cache_time
    import time
    now = time.time()
    if now - _cache_time < 300 and team_name in _cache:
        return _cache.get(team_name, {})

    players = _load_json('players.json')
    injuries = _load_json('injuries.json')

    team_players = []
    for p in players:
        if p.get('team', '') == team_name:
            team_players.append(p)

    if not team_players:
        return {'total_value_m': 0, 'avg_value_m': 0, 'player_count': 0}

    values = [p.get('market_value_m', 0) for p in team_players]
    total_val = sum(values)
    avg_val = total_val / len(values) if values else 0

    # 最佳射手
    scorers = sorted(team_players, key=lambda x: x.get('goals', 0), reverse=True)
    top = scorers[0] if scorers else None

    # 关键缺阵（身价最高的伤员）
    injured_names = set()
    if isinstance(injuries, dict):
        inj_data = injuries.get('data', injuries)
        if isinstance(inj_data, dict):
            for t, names in inj_data.items():
                if t == team_name:
                    injured_names = set(names)

    key_missing = [p['name'] for p in team_players
                   if p.get('name') in injured_names and p.get('market_value_m', 0) > 5]

    result = {
        'team': team_name,
        'total_value_m': round(total_val, 1),
        'avg_value_m': round(avg_val, 1),
        'player_count': len(team_players),
        'top_scorer': {'name': top['name'], 'goals': top.get('goals', 0),
                       'assists': top.get('assists', 0)} if top else None,
        'key_missing': key_missing,
        'squad_strength': round(min(10, total_val / 50), 1),  # 0-10 normalized
    }

    _cache[team_name] = result
    _cache_time = now
    return result


def get_coach_data(team_name: str) -> dict:
    """返回教练数据"""
    coaches = _load_json('coaches.json')
    for c in coaches:
        if c.get('team', '') == team_name:
            return c
    return {'team': team_name, 'name': '', 'win_rate': 50, 'experience_years': 0}


def get_match_player_factor(home: str, away: str) -> dict:
    """
    返回比赛级别球员因子:
    {home_squad_strength, away_squad_strength, home_value_advantage,
     home_goal_threat, away_goal_threat, coach_factor}
    """
    hp = get_team_player_value(home)
    ap = get_team_player_value(away)
    hc = get_coach_data(home)
    ac = get_coach_data(away)

    # 身价优势
    if hp.get('total_value_m', 0) + ap.get('total_value_m', 0) > 0:
        value_adv = (hp.get('total_value_m', 0) - ap.get('total_value_m', 0)) / \
                    max(1, hp.get('total_value_m', 0) + ap.get('total_value_m', 0))
    else:
        value_adv = 0

    # 进球威胁（前锋进球能力）
    home_threat = 50
    away_threat = 50
    if hp.get('top_scorer') and hp['top_scorer'].get('goals', 0) > 0:
        home_threat = 50 + min(30, hp['top_scorer']['goals'] * 3)
    if ap.get('top_scorer') and ap['top_scorer'].get('goals', 0) > 0:
        away_threat = 50 + min(30, ap['top_scorer']['goals'] * 3)

    # 教练因子（win_rate差）
    coach_factor = ((hc.get('win_rate', 50) - ac.get('win_rate', 50)) / 100) * 0.05

    # 伤病惩罚
    injury_penalty_h = len(hp.get('key_missing', [])) * 2
    injury_penalty_a = len(ap.get('key_missing', [])) * 2

    return {
        'home_squad_strength': hp.get('squad_strength', 5),
        'away_squad_strength': ap.get('squad_strength', 5),
        'home_value_advantage': round(value_adv, 3),
        'home_goal_threat': home_threat,
        'away_goal_threat': away_threat,
        'coach_factor': round(coach_factor, 3),
        'home_injury_penalty': injury_penalty_h,
        'away_injury_penalty': injury_penalty_a,
        'has_data': hp.get('player_count', 0) > 0,
    }
