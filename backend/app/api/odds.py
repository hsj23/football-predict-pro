"""
赔率API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models.odds import Odds

router = APIRouter()


class OddsCreate(BaseModel):
    match_id: str
    bookmaker: str
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    handicap: Optional[float] = None
    is_opening: int = 0


def _calc_tendency(odds_obj):
    """计算赔率倾向"""
    ho = float(odds_obj.home_odds) if odds_obj.home_odds else 0
    do = float(odds_obj.draw_odds) if odds_obj.draw_odds else 0
    ao = float(odds_obj.away_odds) if odds_obj.away_odds else 0
    if not (ho and do and ao):
        return None
    h, d, a = 1 / ho, 1 / do, 1 / ao
    total = h + d + a
    ph, pd, pa = h / total, d / total, a / total
    max_p = max(ph, pd, pa)
    if max_p == ph:
        return "home"
    elif max_p == pd:
        return "draw"
    else:
        return "away"


@router.post("/")
async def create_odds(odds: OddsCreate, db: Session = Depends(get_db)):
    """添加赔率"""
    new_odds = Odds(
        match_id=odds.match_id,
        bookmaker=odds.bookmaker,
        home_odds=odds.home_odds,
        draw_odds=odds.draw_odds,
        away_odds=odds.away_odds,
        handicap=odds.handicap,
        is_opening=odds.is_opening,
        collect_time=datetime.now()
    )
    db.add(new_odds)
    db.commit()
    db.refresh(new_odds)
    return {"success": True, "odds_id": new_odds.id}


# 注意: /compare/{match_id} 必须在 /{match_id} 之前注册，否则 "compare" 会被当成 match_id
@router.get("/compare/{match_id}")
async def compare_odds(
    match_id: str,
    db: Session = Depends(get_db)
):
    """对比多家博彩公司赔率"""
    odds_list = db.query(Odds).filter(
        Odds.match_id == match_id
    ).all()

    bookmakers = {}
    for o in odds_list:
        if o.bookmaker not in bookmakers:
            bookmakers[o.bookmaker] = []
        bookmakers[o.bookmaker].append({
            "home_odds": float(o.home_odds) if o.home_odds else None,
            "draw_odds": float(o.draw_odds) if o.draw_odds else None,
            "away_odds": float(o.away_odds) if o.away_odds else None,
            "is_opening": bool(o.is_opening),
            "handicap": float(o.handicap) if o.handicap else None,
        })

    return {
        "match_id": match_id,
        "bookmakers": bookmakers,
        "total_bookmakers": len(bookmakers)
    }


@router.get("/{match_id}/kelly")
async def get_kelly_index(
    match_id: str,
    db: Session = Depends(get_db)
):
    """计算凯利指数"""
    odds_list = db.query(Odds).filter(
        Odds.match_id == match_id,
        Odds.is_opening == 1
    ).all()

    kelly_results = []
    for o in odds_list:
        if o.home_odds and o.draw_odds and o.away_odds:
            try:
                return_rate = 1 / float(o.home_odds) + 1 / float(o.draw_odds) + 1 / float(o.away_odds)
                home_kelly = (1 / float(o.home_odds)) / return_rate
                draw_kelly = (1 / float(o.draw_odds)) / return_rate
                away_kelly = (1 / float(o.away_odds)) / return_rate
                kelly_results.append({
                    "bookmaker": o.bookmaker,
                    "return_rate": round((1 - return_rate) * 100, 2),
                    "home_kelly": round(home_kelly * 100, 2),
                    "draw_kelly": round(draw_kelly * 100, 2),
                    "away_kelly": round(away_kelly * 100, 2)
                })
            except:
                pass

    return {
        "match_id": match_id,
        "kelly_index": kelly_results
    }


@router.get("/{match_id}/analysis")
async def get_odds_analysis(
    match_id: str,
    db: Session = Depends(get_db)
):
    """赔率分析汇总"""
    odds_list = db.query(Odds).filter(
        Odds.match_id == match_id
    ).all()

    if not odds_list:
        return {"error": "暂无赔率数据"}

    opening = [o for o in odds_list if o.is_opening]
    if not opening:
        opening = odds_list

    home_odds_list = [float(o.home_odds) for o in opening if o.home_odds]
    draw_odds_list = [float(o.draw_odds) for o in opening if o.draw_odds]
    away_odds_list = [float(o.away_odds) for o in opening if o.away_odds]

    return {
        "match_id": match_id,
        "bookmakers_count": len(set(o.bookmaker for o in odds_list)),
        "total_odds_count": len(odds_list),
        "avg_home_odds": round(sum(home_odds_list) / len(home_odds_list), 2) if home_odds_list else None,
        "avg_draw_odds": round(sum(draw_odds_list) / len(draw_odds_list), 2) if draw_odds_list else None,
        "avg_away_odds": round(sum(away_odds_list) / len(away_odds_list), 2) if away_odds_list else None,
        "opening_odds": [
            {
                "bookmaker": o.bookmaker,
                "home_odds": float(o.home_odds) if o.home_odds else None,
                "draw_odds": float(o.draw_odds) if o.draw_odds else None,
                "away_odds": float(o.away_odds) if o.away_odds else None,
                "tendency": _calc_tendency(o)
            }
            for o in opening
        ]
    }


@router.get("/{match_id}")
async def get_match_odds(
    match_id: str,
    bookmaker: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取比赛赔率"""
    try:
        query = db.query(Odds).filter(Odds.match_id == match_id)
        if bookmaker:
            query = query.filter(Odds.bookmaker == bookmaker)
        odds = query.all()

        result = []
        for o in odds:
            result.append({
                "id": o.id,
                "match_id": o.match_id,
                "bookmaker": o.bookmaker,
                "home_odds": float(o.home_odds) if o.home_odds else None,
                "draw_odds": float(o.draw_odds) if o.draw_odds else None,
                "away_odds": float(o.away_odds) if o.away_odds else None,
                "handicap": float(o.handicap) if o.handicap else None,
                "is_opening": bool(o.is_opening)
            })

        return {
            "match_id": match_id,
            "odds": result
        }
    except Exception as e:
        return {"error": str(e)}
