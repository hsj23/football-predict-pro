"""
自动数据更新服务
- 使用真实爬虫获取中国体彩数据
- 每天定时更新
"""
import schedule
import time
from datetime import datetime, timedelta
import logging
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.china_lottery import ChinaLotteryCrawler

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'updater.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DataUpdater:
    """数据更新服务"""

    def __init__(self):
        self.running = False
        self.crawler = ChinaLotteryCrawler()

    def update_all_data(self):
        """更新所有数据"""
        logger.info("=" * 50)
        logger.info("开始更新数据...")
        logger.info("=" * 50)

        try:
            # 获取今日比赛
            logger.info("获取今日比赛...")
            matches = self.crawler.get_jczq_matches()

            # 获取历史结果
            logger.info("获取历史开奖结果...")
            results = self.crawler.get_history_results(days=30)

            # 保存到数据库
            logger.info("保存到数据库...")
            self.crawler.save_to_database(matches, results)

            # 统计
            correct = sum(1 for r in results if r['is_correct'] == 1)
            wrong = sum(1 for r in results if r['is_correct'] == 2)
            accuracy = round(correct / (correct + wrong) * 100, 1) if (correct + wrong) > 0 else 0

            logger.info(f"数据更新完成!")
            logger.info(f"今日比赛: {len(matches)} 场")
            logger.info(f"历史结果: {len(results)} 条 (正确:{correct}, 错误:{wrong}, 准确率:{accuracy}%)")
            logger.info(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            logger.error(f"更新失败: {e}")

    def start_scheduler(self):
        """启动定时任务"""
        # 每天早上8:00更新
        schedule.every().day.at("08:00").do(self.update_all_data)
        # 每天下午17:00更新
        schedule.every().day.at("17:00").do(self.update_all_data)
        # 每天晚上21:00更新（比赛开始前后）
        schedule.every().day.at("21:00").do(self.update_all_data)

        logger.info("定时任务已启动:")
        logger.info("  - 每天 08:00 自动更新")
        logger.info("  - 每天 17:00 自动更新")
        logger.info("  - 每天 21:00 自动更新")

        self.running = True
        while self.running:
            schedule.run_pending()
            time.sleep(60)

    def stop(self):
        """停止服务"""
        self.running = False


def run_updater():
    """运行更新服务"""
    updater = DataUpdater()

    # 启动时立即更新一次
    logger.info("启动时更新数据...")
    updater.update_all_data()

    # 然后启动定时任务
    updater.start_scheduler()


if __name__ == "__main__":
    print("=" * 50)
    print("足彩预测系统 - 自动更新服务")
    print("=" * 50)
    print("\n数据来源: 中国体彩")
    print("\n定时更新:")
    print("  - 每天 08:00")
    print("  - 每天 17:00")
    print("  - 每天 21:00")
    print("\n按 Ctrl+C 停止服务\n")

    try:
        run_updater()
    except KeyboardInterrupt:
        print("\n服务已停止")
