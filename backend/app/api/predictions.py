"""
预测API路由 - 简化版
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.prediction import Prediction, PlatformAccuracy
from app.models.match import Match

router = APIRouter()


@router.get("/{match_id}")
async def get_match_predictions(
    match_id: str,
    db: Session = Depends(get_db)
):
    """获取某场比赛的所有预测"""
    predictions = db.query(Prediction).filter(
        Prediction.match_id == match_id
    ).all()

    # 按结果统计
    result_stats = {"home": 0, "draw": 0, "away": 0}

    for p in predictions:
        if p.prediction_result in result_stats:
            result_stats[p.prediction_result] += 1

    total = sum(result_stats.values())

    return {
        "match_id": match_id,
        "total_platforms": len(predictions),
        "result_distribution": result_stats,
        "predictions": [p.to_dict() for p in predictions]
    }


@router.get("/{match_id}/analysis")
async def get_prediction_analysis(
    match_id: str,
    db: Session = Depends(get_db)
):
    """获取单场比赛的综合预测分析"""
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="比赛不存在")

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'services'))
    from prediction_service import PredictionService

    predictor = PredictionService()
    pred = predictor.generate_prediction(
        match.home_team_name, match.away_team_name,
        match.league_name, match_id=match_id
    )
    p = pred['prediction']

    # 平台聚合
    platform_votes = pred.get('platform_votes', {})
    total_votes = sum(platform_votes.values()) or 1
    platform_aggregation = {
        'votes': platform_votes,
        'percentages': {
            'home': round(platform_votes.get('home', 0) / total_votes * 100, 1),
            'draw': round(platform_votes.get('draw', 0) / total_votes * 100, 1),
            'away': round(platform_votes.get('away', 0) / total_votes * 100, 1),
        },
        'total_votes': sum(platform_votes.values()),
        'platform_details': [
            {
                'platform': pl.get('platform', '?'),
                'prediction': pl.get('prediction', '?'),
                'confidence': pl.get('confidence', 0),
                'accuracy': pl.get('accuracy', None),
            }
            for pl in pred.get('platform_predictions', [])
        ]
    }

    return {
        'match_info': match.to_dict(),
        'final_prediction': {
            'prediction': p['prediction'],
            'prediction_name': p.get('prediction_name', ''),
            'confidence': p['confidence'],
            'confidence_level': '高' if p['confidence'] >= 55 else ('中' if p['confidence'] >= 40 else '低'),
            'probabilities': {
                'home': p.get('probabilities', {}).get('home', 33),
                'draw': p.get('probabilities', {}).get('draw', 33),
                'away': p.get('probabilities', {}).get('away', 34),
            },
            'predicted_score': p.get('predicted_score', ''),
        },
        'predictions': {
            'platform_aggregation': platform_aggregation,
            'odds_analysis': pred.get('odds_analysis', {}),
            'team_analysis': pred.get('team_analysis', {}),
            'h2h_analysis': pred.get('h2h_analysis', {}),
            'analysis_summary': pred.get('analysis_summary', []),
        }
    }


@router.get("/platforms/accuracy")
async def get_platform_accuracy(
    league: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取各平台准确率统计"""
    query = db.query(PlatformAccuracy)
    if league:
        query = query.filter(PlatformAccuracy.league == league)

    results = query.all()

    return {
        "platforms": [
            {
                "platform": r.platform,
                "league": r.league,
                "total_predictions": r.total_predictions,
                "correct_predictions": r.correct_predictions,
                "accuracy_rate": float(r.accuracy_rate) if r.accuracy_rate else 0
            }
            for r in results
        ]
    }
