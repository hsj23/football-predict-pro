"""
统计API路由
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app.models.match import Match
from app.models.prediction import Prediction, PredictionHistory
from app.models.team import Team

router = APIRouter()


@router.get("/overview")
async def get_statistics_overview(db: Session = Depends(get_db)):
    """获取统计概览 - 使用真实数据"""
    # 比赛统计
    total_matches = db.query(Match).count()

    # 今日比赛
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    cutoff = datetime.now() - timedelta(hours=3)
    today_matches = db.query(Match).filter(
        Match.match_time >= str(today),
        Match.match_time < str(tomorrow),
        Match.match_time > cutoff
    ).count()

    # 预测统计 from prediction_history
    total_predictions = db.query(PredictionHistory).count()
    correct = db.query(PredictionHistory).filter(
        PredictionHistory.is_correct == 1
    ).count()
    wrong = db.query(PredictionHistory).filter(
        PredictionHistory.is_correct == 2
    ).count()
    decided = correct + wrong
    accuracy_rate = round(correct / decided * 100, 1) if decided > 0 else 0

    # 近7天准确率
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent = db.query(PredictionHistory).filter(
        PredictionHistory.match_date >= seven_days_ago,
        PredictionHistory.is_correct.in_([1, 2])
    ).all()
    recent_total = len(recent)
    recent_correct = sum(1 for r in recent if r.is_correct == 1)
    recent_accuracy = round(recent_correct / recent_total * 100, 1) if recent_total > 0 else 0

    # 球队统计
    total_teams = db.query(Team).count()

    return {
        "matches": {
            "total": total_matches,
            "today": today_matches
        },
        "predictions": {
            "total": total_predictions,
            "correct": correct,
            "wrong": wrong,
            "accuracy_rate": accuracy_rate,
            "recent_7d_accuracy": recent_accuracy
        },
        "teams": {
            "total": total_teams
        }
    }


@router.get("/hot/matches")
async def get_hot_matches(
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """热门比赛"""
    matches = db.query(Match).order_by(Match.match_time.desc()).limit(limit).all()

    return {
        "hot_matches": [
            {
                **m.to_dict(),
                "prediction_count": 3
            }
            for m in matches
        ]
    }


@router.get("/roi")
async def get_roi_evaluation():
    """ROI 评估 — 回测历史预测的投资回报率"""
    from ml.evaluation import backtest_from_db
    result = backtest_from_db()
    if result is None:
        return {"error": "暂无足够历史数据进行回测"}
    return result


@router.get("/calibration")
async def get_calibration():
    """校准质量评估 — 模型置信度是否准确"""
    from ml.evaluation import evaluate_calibration
    from app.db_helper import db_cursor

    try:
        with db_cursor() as cur:
            cur.execute('''
                SELECT prediction_result, actual_result, confidence, detail_json
                FROM prediction_history
                WHERE is_correct IN (1, 2)
                  AND actual_result IS NOT NULL
                  AND detail_json IS NOT NULL
                ORDER BY match_date DESC LIMIT 200
            ''')
            rows = cur.fetchall()

        import json
        predictions = []
        for pred_result, actual_result, confidence, detail_json in rows:
            probs = {}
            if detail_json:
                try:
                    detail = json.loads(detail_json)
                    probs = detail.get('probabilities', {})
                except Exception:
                    pass
            predictions.append({
                'prediction': pred_result,
                'actual_result': actual_result,
                'confidence': float(confidence) if confidence else 50,
                'probabilities': probs,
            })

        return evaluate_calibration(predictions)
    except Exception as e:
        return {"error": str(e)}
