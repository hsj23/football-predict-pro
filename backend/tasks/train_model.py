"""
训练模型任务 - 使用真实比赛数据训练
"""
from datetime import datetime
import logging
import os
import sys

logger = logging.getLogger(__name__)

# 模型保存路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "ml", "models")


def train_model_task():
    """训练预测模型（使用真实数据）"""
    logger.info("=" * 50)
    logger.info("开始训练预测模型...")
    logger.info("=" * 50)

    try:
        sys.path.insert(0, os.path.join(BASE_DIR))
        from ml.model_trainer import ModelTrainer

        trainer = ModelTrainer()
        results = trainer.train()

        if 'error' in results:
            logger.error(f"训练失败: {results['error']}")
            return

        accuracy = results.get('accuracy', 0)
        logger.info(f"模型训练完成: 准确率 {accuracy:.2%}")
        logger.info(f"交叉验证: {results.get('cv_mean', 0):.2%} ± {results.get('cv_std', 0):.2%}")
        if results.get('odds_baseline_accuracy'):
            logger.info(f"赔率基线准确率: {results['odds_baseline_accuracy']:.2%}")

        # 各类别准确率
        per_class = results.get('per_class_accuracy', {})
        if per_class:
            logger.info(f"各类别准确率: { {k: f'{v:.1%}' for k, v in per_class.items()} }")

        # 保存模型
        os.makedirs(MODEL_PATH, exist_ok=True)
        model_file = os.path.join(MODEL_PATH, "xgboost_model.pkl")
        trainer.save_model(model_file)
        logger.info(f"XGBoost模型已保存: {model_file}")

        # 同时训练神经网络
        try:
            logger.info("-" * 40)
            logger.info("训练神经网络模型...")
            from ml.neural_predictor import NeuralPredictionModel
            from ml.feature_engineering import FeatureEngineer

            # 加载相同的训练数据
            import json
            results_file = os.path.join(BASE_DIR, '..', 'data', 'jczq_results.json')
            if not os.path.exists(results_file):
                results_file = os.path.join(BASE_DIR, 'data', 'jczq_results.json')

            if os.path.exists(results_file):
                with open(results_file, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, dict):
                    raw_data = raw_data.get('matches', raw_data.get('results', []))

                valid_matches = []
                for m in raw_data:
                    if m.get('full_score') and ':' in m.get('full_score', ''):
                        valid_matches.append(m)

                if len(valid_matches) >= 50:
                    nn_model = NeuralPredictionModel()
                    nn_accuracy = nn_model.train(valid_matches, epochs=150)
                    logger.info(f"神经网络训练完成: 验证准确率 {nn_accuracy:.1f}%")
                else:
                    logger.warning(f"神经网络训练数据不足 ({len(valid_matches)})")
        except Exception as e:
            logger.error(f"神经网络训练失败: {e}")

    except Exception as e:
        logger.error(f"模型训练失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    train_model_task()
