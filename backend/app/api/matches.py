"""
比赛API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from app.database import get_db
from app.models.match import Match

router = APIRouter()


class MatchCreate(BaseModel):
    match_id: str
    league_name: str
    home_team_name: str
    away_team_name: str
    match_time: str
    status: str = "scheduled"


@router.get("/")
async def get_matches(
    league: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """获取比赛列表"""
    query = db.query(Match)

    if league:
        query = query.filter(Match.league_name.contains(league))

    if date:
        query = query.filter(
            Match.match_time >= date,
            Match.match_time < date + ' 23:59:59'
        )

    from datetime import timedelta
    cutoff = datetime.now() - timedelta(hours=3)
    query = query.filter(Match.match_time > cutoff)

    total = query.count()
    matches = query.order_by(Match.match_time.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [m.to_dict() for m in matches]
    }


@router.get("/{match_id}")
async def get_match(match_id: str, db: Session = Depends(get_db)):
    """获取比赛详情"""
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if not match:
        return {"error": "比赛不存在"}
    return match.to_dict()


@router.get("/today/list")
async def get_today_matches(db: Session = Depends(get_db)):
    """获取今日比赛"""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    cutoff = datetime.now() - timedelta(hours=3)
    matches = db.query(Match).filter(
        Match.match_time >= today,
        Match.match_time < tomorrow,
        Match.match_time > cutoff
    ).order_by(Match.match_time).all()

    return {
        "date": today.isoformat(),
        "count": len(matches),
        "matches": [m.to_dict() for m in matches]
    }


@router.post("/")
async def create_match(match: MatchCreate, db: Session = Depends(get_db)):
    """添加比赛"""
    # 检查是否已存在
    existing = db.query(Match).filter(Match.match_id == match.match_id).first()
    if existing:
        return {"error": "比赛ID已存在"}

    # 解析时间
    try:
        match_time = datetime.fromisoformat(match.match_time.replace('Z', '+00:00'))
    except:
        match_time = datetime.now()

    new_match = Match(
        match_id=match.match_id,
        league_name=match.league_name,
        home_team_name=match.home_team_name,
        away_team_name=match.away_team_name,
        match_time=match_time,
        status=match.status
    )

    db.add(new_match)
    db.commit()
    db.refresh(new_match)

    return {"success": True, "match": new_match.to_dict()}


@router.delete("/{match_id}")
async def delete_match(match_id: str, db: Session = Depends(get_db)):
    """删除比赛"""
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if not match:
        return {"error": "比赛不存在"}

    db.delete(match)
    db.commit()
    return {"success": True}
