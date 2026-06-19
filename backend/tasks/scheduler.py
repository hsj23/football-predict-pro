"""
定时任务调度器
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskScheduler:
    """任务调度器"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        logger.info("任务调度器已启动")

    def add_job(self, func, trigger, **kwargs):
        """添加定时任务"""
        self.scheduler.add_job(func, trigger, **kwargs)
        logger.info(f"添加定时任务: {func.__name__}")

    def add_interval_job(self, func, minutes=30, **kwargs):
        """添加间隔任务"""
        self.add_job(func, IntervalTrigger(minutes=minutes), **kwargs)

    def add_cron_job(self, func, cron_expr, **kwargs):
        """添加Cron任务"""
        self.add_job(func, CronTrigger.from_crontab(cron_expr), **kwargs)

    def get_jobs(self):
        """获取所有任务"""
        return self.scheduler.get_jobs()

    def remove_job(self, job_id):
        """移除任务"""
        self.scheduler.remove_job(job_id)

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()


# 全局调度器实例
scheduler = TaskScheduler()


def init_tasks():
    """初始化所有定时任务，启动时立即执行一次"""
    from tasks.update_odds import update_odds_task
    from tasks.update_predictions import update_predictions_task
    from tasks.update_matches import update_matches_task
    from tasks.update_results import update_results_task
    from tasks.train_model import train_model_task

    # 启动时立即执行（在后台线程，不阻塞服务启动）
    import threading
    def _run_all():
        for name, fn in [("赔率", update_odds_task), ("预测", update_predictions_task),
                         ("比赛列表", update_matches_task), ("结果同步", update_results_task)]:
            try:
                logger.info(f"启动时立即更新: {name}")
                fn()
            except Exception as e:
                logger.warning(f"启动更新 {name} 失败: {e}")
        # 清理 prediction_history 中的重复记录
        try:
            from app.db_helper import db_cursor
            with db_cursor() as cur:
                cur.execute("""DELETE t1 FROM prediction_history t1
                    INNER JOIN prediction_history t2
                    WHERE t1.match_id = t2.match_id AND t1.id < t2.id""")
            logger.info("已清理 prediction_history 重复记录")
        except Exception as e:
            logger.debug(f"清理重复记录跳过: {e}")
    threading.Thread(target=_run_all, daemon=True).start()

    # 每30分钟更新赔率
    scheduler.add_interval_job(update_odds_task, minutes=30)

    # 每1小时更新预测
    scheduler.add_interval_job(update_predictions_task, minutes=60)

    # 每3小时同步完场比分
    scheduler.add_interval_job(update_results_task, minutes=180)

    # 每天6:00更新比赛列表
    scheduler.add_cron_job(update_matches_task, "0 6 * * *")

    # 每周训练一次模型
    scheduler.add_cron_job(train_model_task, "0 3 * * 0")  # 周日凌晨3点

    logger.info("定时任务初始化完成（已触发启动时立即刷新）")


if __name__ == "__main__":
    init_tasks()

    # 保持运行
    try:
        while True:
            pass
    except KeyboardInterrupt:
        scheduler.shutdown()
