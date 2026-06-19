"""
历史预测API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import Optional
from datetime import datetime, timedelta
from app.database import get_db
from app.models.prediction import PredictionHistory

router = APIRouter()


@router.get("/list")
async def get_history_list(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    league: Optional[str] = Query(None, description="联赛筛选"),
    result: Optional[str] = Query(None, description="结果筛选: correct/wrong"),
    team: Optional[str] = Query(None, description="队伍名称筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取历史预测列表 - 支持多天查询"""
    query = db.query(PredictionHistory)

    # 日期筛选 - 默认近30天
    if start_date:
        query = query.filter(PredictionHistory.match_date >= start_date)
    else:
        default_start = datetime.now() - timedelta(days=30)
        query = query.filter(PredictionHistory.match_date >= default_start)

    if end_date:
        query = query.filter(PredictionHistory.match_date <= end_date + " 23:59:59")

    # 联赛筛选
    if league:
        query = query.filter(PredictionHistory.league == league)

    # 结果筛选
    if result == "correct":
        query = query.filter(PredictionHistory.is_correct == 1)
    elif result == "wrong":
        query = query.filter(PredictionHistory.is_correct == 2)

    # 队伍筛选 - 匹配主队或客队
    if team:
        query = query.filter(
            (PredictionHistory.home_team.contains(team)) |
            (PredictionHistory.away_team.contains(team))
        )

    # 总数
    total = query.count()

    # 分页
    records = query.order_by(PredictionHistory.match_date.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [r.to_dict() for r in records]
    }


@router.get("/statistics")
async def get_history_statistics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取历史预测统计数据 — SQL聚合"""
    from sqlalchemy import case
    date_start = start_date or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    date_end = (end_date + " 23:59:59") if end_date else None

    q = db.query(PredictionHistory).filter(PredictionHistory.match_date >= date_start)
    if date_end:
        q = q.filter(PredictionHistory.match_date <= date_end)

    # 一次查询拿总数/正确/错误/待定
    s = db.query(
        func.count(PredictionHistory.id).label('total'),
        func.sum(case((PredictionHistory.is_correct == 1, 1), else_=0)).label('correct'),
        func.sum(case((PredictionHistory.is_correct == 2, 1), else_=0)).label('wrong'),
    ).filter(PredictionHistory.match_date >= date_start)
    if date_end:
        s = s.filter(PredictionHistory.match_date <= date_end)
    s = s.first()
    total, correct, wrong = int(s.total or 0), int(s.correct or 0), int(s.wrong or 0)

    # 近7天
    r7 = db.query(
        func.count(PredictionHistory.id),
        func.sum(case((PredictionHistory.is_correct == 1, 1), else_=0)),
    ).filter(PredictionHistory.match_date >= datetime.now() - timedelta(days=7),
             PredictionHistory.is_correct.in_([1, 2])).first()
    r7t, r7c = int(r7[0] or 1), int(r7[1] or 0)
    recent_accuracy = round(r7c / r7t * 100, 1) if r7t > 0 else 0

    # 预测类型统计
    type_rows = db.query(
        PredictionHistory.prediction_result,
        func.count(PredictionHistory.id),
        func.sum(case((PredictionHistory.is_correct == 1, 1), else_=0)),
    ).filter(PredictionHistory.prediction_result.in_(['home', 'draw', 'away']))\
     .group_by(PredictionHistory.prediction_result).all()
    pt_map = {'home': '主胜', 'draw': '平局', 'away': '客胜'}
    prediction_type_accuracy = [
        {"type": pt, "name": pt_map.get(pt, pt), "total": int(t), "correct": int(c or 0),
         "accuracy": round(c/t*100, 1) if t else 0}
        for pt, t, c in type_rows
    ]

    # 联赛统计
    league_rows = db.query(
        PredictionHistory.league,
        func.count(PredictionHistory.id),
        func.sum(case((PredictionHistory.is_correct == 1, 1), else_=0)),
    ).filter(PredictionHistory.league.isnot(None))\
     .group_by(PredictionHistory.league).order_by(func.count(PredictionHistory.id).desc()).limit(12).all()
    league_accuracy = [
        {"league": lg, "total": int(t), "correct": int(c or 0), "accuracy": round(c/t*100,1) if t else 0}
        for lg, t, c in league_rows
    ]

    return {
        "summary": {
            "total": total, "correct": correct, "wrong": wrong,
            "pending": total - correct - wrong,
            "accuracy": round(correct / (correct + wrong) * 100, 1) if (correct + wrong) > 0 else 0,
            "recent_7_days_accuracy": recent_accuracy
        },
        "league_accuracy": league_accuracy,
        "prediction_type_accuracy": prediction_type_accuracy,
        "daily_stats": []
    }


@router.get("/dates")
async def get_available_dates(db: Session = Depends(get_db)):
    """获取有历史记录的日期列表"""
    thirty_days_ago = datetime.now() - timedelta(days=30)

    dates = db.query(
        func.date(PredictionHistory.match_date).label("date"),
        func.count(PredictionHistory.id).label("count")
    ).filter(
        PredictionHistory.match_date >= thirty_days_ago
    ).group_by(
        func.date(PredictionHistory.match_date)
    ).order_by(
        func.date(PredictionHistory.match_date).desc()
    ).all()

    return {
        "dates": [
            {"date": str(d.date), "count": d.count}
            for d in dates
        ]
    }


@router.post("/save")
async def save_prediction_history(
    match_id: str,
    match_date: str,
    league: str,
    home_team: str,
    away_team: str,
    prediction_result: str,
    prediction_name: str,
    confidence: float = 0,
    predicted_score: str = "",
    db: Session = Depends(get_db)
):
    """保存预测记录到历史"""
    record = PredictionHistory(
        match_id=match_id,
        match_date=datetime.strptime(match_date, "%Y-%m-%d %H:%M"),
        league=league,
        home_team=home_team,
        away_team=away_team,
        prediction_result=prediction_result,
        prediction_name=prediction_name,
        confidence=confidence,
        predicted_score=predicted_score,
        is_correct=0  # 待验证
    )
    db.add(record)
    db.commit()

    return {"success": True, "id": record.id}


@router.post("/update-result")
async def update_match_result(
    match_id: str,
    home_score: int,
    away_score: int,
    db: Session = Depends(get_db)
):
    """更新比赛结果"""
    record = db.query(PredictionHistory).filter(
        PredictionHistory.match_id == match_id
    ).order_by(PredictionHistory.id.desc()).first()

    if not record:
        return {"success": False, "message": "记录不存在"}

    # 更新比分
    record.home_score = home_score
    record.away_score = away_score
    record.actual_score = f"{home_score}-{away_score}"

    # 计算实际结果
    if home_score > away_score:
        record.actual_result = "home"
    elif home_score < away_score:
        record.actual_result = "away"
    else:
        record.actual_result = "draw"

    # 判断预测是否正确
    if record.actual_result == record.prediction_result:
        record.is_correct = 1
    else:
        record.is_correct = 2

    db.commit()

    return {
        "success": True,
        "actual_result": record.actual_result,
        "is_correct": record.is_correct
    }


@router.get("/detail/{match_id}")
async def get_match_detail(match_id: str, db: Session = Depends(get_db)):
    """获取历史比赛详细预测数据 — 只返回最新版本"""
    record = db.query(PredictionHistory).filter(
        PredictionHistory.match_id == match_id
    ).order_by(PredictionHistory.id.desc()).first()

    if not record:
        return {"error": "比赛记录不存在"}

    # 获取该比赛所有历史预测版本（供调试）
    history_versions = db.query(PredictionHistory).filter(
        PredictionHistory.match_id == match_id
    ).order_by(PredictionHistory.id.desc()).all()

    prediction_history = []
    for v in history_versions:
        ver_info = {
            'id': v.id,
            'prediction': v.prediction_result or 'home',
            'prediction_name': v.prediction_name or '主胜',
            'confidence': float(v.confidence or 50),
            'predicted_score': v.predicted_score or '',
            'created_at': v.created_at.strftime("%m-%d %H:%M") if v.created_at else '',
        }
        if v.detail_json:
            try:
                import json as _json
                dc = _json.loads(v.detail_json)
                ver_info['probabilities'] = dc.get('probabilities', {})
                ver_info['platform_predictions'] = dc.get('platform_predictions', [])
                ver_info['analysis_summary'] = dc.get('analysis_summary', [])
            except: pass
        prediction_history.append(ver_info)

    # 如果有缓存，直接返回
    if record.detail_json:
        import json as _json
        try:
            cached = _json.loads(record.detail_json)
            return {
                'match_id': match_id,
                'league_name': record.league,
                'home_team_name': record.home_team,
                'away_team_name': record.away_team,
                'match_time': record.match_date.strftime("%Y-%m-%d %H:%M:%S") if record.match_date else '',
                'actual_result': record.actual_result,
                'actual_score': record.actual_score,
                'home_score': record.home_score,
                'away_score': record.away_score,
                'is_correct': record.is_correct,
                'prediction': {
                    'prediction': record.prediction_result,
                    'prediction_name': record.prediction_name,
                    'confidence': float(record.confidence) if record.confidence else 0,
                    'probabilities': cached.get('probabilities', {}),
                    'predicted_score': record.predicted_score or '',
                },
                'platform_predictions': cached.get('platform_predictions', []),
                'odds_analysis': cached.get('odds_analysis', {}),
                'team_analysis': cached.get('team_analysis', {}),
                'h2h_analysis': cached.get('h2h_analysis', {}),
                'analysis_summary': cached.get('analysis_summary', []),
                'news_analysis': cached.get('news_analysis', {}),
                'prediction_history': prediction_history,
                'from_cache': True,
            }
        except:
            pass

    # 没缓存 → 返回基本信息，不跑引擎（避免卡顿）
    return {
        'match_id': match_id,
        'league_name': record.league,
        'home_team_name': record.home_team,
        'away_team_name': record.away_team,
        'match_time': record.match_date.strftime("%Y-%m-%d %H:%M:%S") if record.match_date else '',
        'actual_result': record.actual_result,
        'actual_score': record.actual_score,
        'home_score': record.home_score,
        'away_score': record.away_score,
        'is_correct': record.is_correct,
        'prediction': {
            'prediction': record.prediction_result or 'home',
            'prediction_name': record.prediction_name or '主胜',
            'confidence': float(record.confidence or 50),
            'probabilities': {},
            'predicted_score': record.predicted_score or '',
        },
        'platform_predictions': [],
        'odds_analysis': {},
        'team_analysis': {},
        'h2h_analysis': {},
        'analysis_summary': ['本条记录暂无详细预测数据，新预测将自动包含完整分析'],
        'prediction_history': prediction_history,
        'from_cache': False,
    }


@router.delete("/cleanup")
async def cleanup_old_records(db: Session = Depends(get_db)):
    """清理30天前的旧记录"""
    thirty_days_ago = datetime.now() - timedelta(days=30)

    deleted = db.query(PredictionHistory).filter(
        PredictionHistory.match_date < thirty_days_ago
    ).delete()

    db.commit()

    return {"success": True, "deleted_count": deleted}
