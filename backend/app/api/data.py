"""
数据更新API - 历史数据生成 + 增量刷新
"""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from datetime import datetime, timedelta

router = APIRouter()


@router.post("/refresh-history")
async def refresh_history(db: Session = Depends(get_db)):
    """已禁用 — 模拟数据生成会造成虚假历史记录"""
    return {
        "success": False,
        "message": "此接口已禁用。历史数据仅来自体彩官方API自动回填，不再生成模拟数据。",
    }


@router.post("/refresh-today")
async def refresh_today(db: Session = Depends(get_db)):
    """刷新今日比赛和预测 - 轻量级，不重新生成全部历史"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.models.prediction import PredictionHistory
    from app.models.match import Match
    from services.prediction_service import PredictionService
    from datetime import datetime

    predictor = PredictionService()
    today = datetime.now().strftime('%Y-%m-%d')
    three_days_later = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')

    # 获取今日及未来3天比赛（排除3小时前已开赛的）
    cutoff = datetime.now() - timedelta(hours=3)
    matches = db.query(Match).filter(
        Match.match_time >= today,
        Match.match_time < three_days_later + ' 23:59:59',
        Match.match_time > cutoff
    ).all()

    if not matches:
        return {"success": False, "message": "今日无比赛数据，请先更新比赛列表"}

    new_count = 0
    update_count = 0

    for m in matches:
        match_id = m.match_id
        pred = predictor.generate_prediction(m.home_team_name, m.away_team_name, m.league_name)
        p = pred['prediction']

        existing = db.query(PredictionHistory).filter(
            PredictionHistory.match_id == match_id
        ).first()

        if existing:
            existing.prediction_result = p['prediction']
            existing.prediction_name = p['prediction_name']
            existing.confidence = p['confidence']
            update_count += 1
        else:
            record = PredictionHistory(
                match_id=match_id,
                match_date=today,
                league=m.league_name,
                home_team=m.home_team_name,
                away_team=m.away_team_name,
                prediction_result=p['prediction'],
                prediction_name=p['prediction_name'],
                confidence=p['confidence'],
                is_correct=0,
            )
            db.add(record)
            new_count += 1

    db.commit()

    return {
        "success": True,
        "message": f"今日预测已更新",
        "matches": len(matches),
        "new": new_count,
        "updated": update_count,
    }


@router.get("/status")
async def get_update_status():
    from datetime import datetime
    from app.models.prediction import PredictionHistory
    from sqlalchemy import func
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        latest = db.query(func.max(PredictionHistory.created_at)).scalar()
        total = db.query(func.count(PredictionHistory.id)).scalar()
        jan_first = db.query(func.count(PredictionHistory.id)).filter(
            PredictionHistory.match_date >= '2026-01-01'
        ).scalar()
        return {
            "last_update": latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None,
            "total_records": total,
            "records_since_2026": jan_first,
        }
    finally:
        db.close()


@router.post("/fetch-upcoming")
async def fetch_upcoming():
    """从体彩官方API拉取即将开赛的比赛（未来比赛）"""
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from services.api_updater import fetch_upcoming_matches
    try:
        count = fetch_upcoming_matches()
        return {"success": True, "message": f"已拉取 {count} 场比赛", "count": count}
    except Exception as e:
        return {"success": False, "message": str(e)}
