"""
任务模块初始化
"""
from tasks.scheduler import scheduler, init_tasks
from tasks.update_odds import update_odds_task
from tasks.update_predictions import update_predictions_task
from tasks.update_matches import update_matches_task
from tasks.train_model import train_model_task

__all__ = [
    "scheduler",
    "init_tasks",
    "update_odds_task",
    "update_predictions_task",
    "update_matches_task",
    "train_model_task"
]
