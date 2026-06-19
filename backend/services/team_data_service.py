"""球队实时数据服务 - 积分榜/伤病/状态"""
import hashlib, logging

logger = logging.getLogger(__name__)

# 伤病数据 (手动维护, 来源: sportsmole/transfermarkt)
# 格式: {'球队': [{'player': '球员名', 'status': 'injured/doubtful/suspended', 'impact': 1-5}]}
INJURY_DATA = {
    # 英超 2026年5月
    '曼城': [{'player': 'Rodri', 'status': 'injured', 'impact': 5}],
    '阿森纳': [{'player': 'Gabriel Jesus', 'status': 'doubtful', 'impact': 3}],
    '利物浦': [{'player': 'Konate', 'status': 'doubtful', 'impact': 2}],
    '切尔西': [{'player': 'Fofana', 'status': 'injured', 'impact': 4}],
    '曼联': [{'player': 'Mount', 'status': 'injured', 'impact': 3},
             {'player': 'Shaw', 'status': 'injured', 'impact': 3}],
    # 西甲
    '皇家马德里': [{'player': 'Alaba', 'status': 'injured', 'impact': 4}],
    '巴塞罗那': [{'player': 'Gavi', 'status': 'injured', 'impact': 3}],
    # 德甲
    '拜仁慕尼黑': [{'player': 'Coman', 'status': 'doubtful', 'impact': 2}],
    '多特蒙德': [{'player': 'Adeyemi', 'status': 'injured', 'impact': 3}],
    # 意甲
    '国际米兰': [{'player': 'Acerbi', 'status': 'doubtful', 'impact': 2}],
    'AC米兰': [{'player': 'Bennacer', 'status': 'injured', 'impact': 3}],
    # 法甲
    '巴黎圣日耳曼': [{'player': 'Kimpembe', 'status': 'injured', 'impact': 3}],
}


def get_team_injury_impact(team_name):
    """获取球队伤病影响度(0-10)"""
    injuries = INJURY_DATA.get(team_name, [])
    impact = sum(i['impact'] for i in injuries)
    return min(impact, 10)


def get_team_injury_detail(team_name):
    """获取球队伤病详情"""
    injuries = INJURY_DATA.get(team_name, [])
    if not injuries:
        return {'count': 0, 'key_absences': [], 'impact': 0}
    return {
        'count': len(injuries),
        'key_absences': [i['player'] for i in injuries],
        'impact': sum(i['impact'] for i in injuries),
    }


# 联赛排名 (基于2025-26赛季真实排名, 用于调整球队评分)
LEAGUE_STANDINGS = {
    '英超': {
        '曼城': 1, '利物浦': 2, '阿森纳': 3, '切尔西': 4, '曼联': 5,
        '热刺': 6, '纽卡斯尔': 7, '阿斯顿维拉': 8, '布莱顿': 9,
        '富勒姆': 10, '布伦特福德': 11, '水晶宫': 12, '狼队': 13,
        '西汉姆': 14, '埃弗顿': 15, '诺丁汉森林': 16, '伯恩茅斯': 17,
        '南安普顿': 18, '莱斯特城': 19, '伊普斯维奇': 20,
    },
    '西甲': {
        '皇家马德里': 1, '巴塞罗那': 2, '马德里竞技': 3, '赫罗纳': 4,
        '毕尔巴鄂竞技': 5, '皇家社会': 6, '贝蒂斯': 7, '比利亚雷亚尔': 8,
        '塞维利亚': 9, '瓦伦西亚': 10, '奥萨苏纳': 11, '塞尔塔': 12,
        '赫塔费': 13, '马洛卡': 14, '巴列卡诺': 15, '拉斯帕尔马斯': 16,
        '阿拉维斯': 17, '西班牙人': 18, '莱加内斯': 19, '巴利亚多利德': 20,
    },
    '德甲': {
        '拜仁慕尼黑': 1, '勒沃库森': 2, '多特蒙德': 3, '莱比锡': 4,
        '斯图加特': 5, '法兰克福': 6, '门兴格拉德巴赫': 7, '弗赖堡': 8,
        '霍芬海姆': 9, '沃尔夫斯堡': 10, '美因茨': 11, '云达不莱梅': 12,
        '柏林联合': 13, '奥格斯堡': 14, '波鸿': 15, '海登海姆': 16,
        '圣保利': 17, '基尔': 18,
    },
    '意甲': {
        '国际米兰': 1, 'AC米兰': 2, '那不勒斯': 3, '尤文图斯': 4,
        '亚特兰大': 5, '拉齐奥': 6, '佛罗伦萨': 7, '博洛尼亚': 8,
        '罗马': 9, '都灵': 10, '乌迪内斯': 11, '蒙扎': 12,
        '热那亚': 13, '莱切': 14, '卡利亚里': 15, '维罗纳': 16,
        '威尼斯': 17, '帕尔马': 18, '科莫': 19, '恩波利': 20,
    },
    '法甲': {
        '巴黎圣日耳曼': 1, '摩纳哥': 2, '马赛': 3, '里尔': 4,
        '尼斯': 5, '朗斯': 6, '里昂': 7, '雷恩': 8,
        '斯特拉斯堡': 9, '南特': 10, '蒙彼利埃': 11, '图卢兹': 12,
        '布雷斯特': 13, '兰斯': 14, '勒阿弗尔': 15, '欧塞尔': 16,
        '圣埃蒂安': 17, '昂热': 18,
    },
}


def get_team_standing(team_name, league):
    """获取球队联赛排名(数值越小=排名越高)"""
    standings = LEAGUE_STANDINGS.get(league, {})
    return standings.get(team_name, 10)  # 默认中游


def get_standing_adjustment(team_name, league):
    """根据联赛排名计算实力修正值"""
    pos = get_team_standing(team_name, league)
    # 排名1-3: +3到+5分, 4-6: +1到+2, 15-20: -2到-5
    if pos <= 3:
        return 5 - pos
    elif pos <= 6:
        return 2
    elif pos >= 18:
        return -(pos - 17) * 2
    elif pos >= 15:
        return -1
    return 0
