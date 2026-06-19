"""
模型训练模块 - 使用真实比赛数据训练XGBoost
"""
import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import xgboost as xgb
from ml.feature_engineering import FeatureEngineer
from app.config import ML_CONFIG
import logging

logger = logging.getLogger(__name__)

# 数据路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_FILE = os.path.join(DATA_DIR, 'jczq_results.json')
TRAINING_FILE = os.path.join(DATA_DIR, 'training_data.json')


class ModelTrainer:
    """模型训练器 - 基于真实数据"""

    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_engineer = FeatureEngineer()
        self.model_type = ML_CONFIG.get("model_type", "xgboost")

    def _load_real_results(self) -> List[Dict]:
        """加载真实比赛结果数据"""
        if not os.path.exists(RESULTS_FILE):
            logger.warning(f"数据文件不存在: {RESULTS_FILE}")
            return []

        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = data.get('matches', data.get('results', []))

        # 只保留有比分的结果
        valid = []
        for m in data:
            full_score = m.get('full_score', '')
            if full_score and ':' in full_score:
                # 检查比分是否有效（包含数字）
                parts = full_score.split(':')
                if len(parts) == 2:
                    try:
                        int(parts[0])
                        int(parts[1])
                        valid.append(m)
                    except ValueError:
                        continue

        logger.info(f"加载 {len(valid)} 条有效比赛记录 (共 {len(data)} 条)")
        return valid

    def _load_training_data(self, data_path: str = None) -> Tuple[np.ndarray, np.ndarray]:
        """加载训练数据"""
        # 优先从指定路径加载
        if data_path and os.path.exists(data_path):
            if data_path.endswith('.csv'):
                df = pd.read_csv(data_path)
                if 'result' in df.columns:
                    X = df.drop('result', axis=1).values
                    y = df['result'].values
                    return X, y
            elif data_path.endswith('.json'):
                with open(data_path, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, dict):
                    raw_data = raw_data.get('matches', raw_data.get('results', []))
            else:
                raw_data = []
        else:
            # 优先从 training_data.json 加载（更大的数据集）
            if os.path.exists(TRAINING_FILE):
                with open(TRAINING_FILE, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, dict):
                    raw_data = raw_data.get('matches', raw_data.get('results', []))
                logger.info(f"从 training_data.json 加载 {len(raw_data)} 条记录")
            else:
                # 加载 jczq_results.json
                raw_data = self._load_real_results()

        if len(raw_data) == 0:
            logger.error("没有可用的训练数据")
            return np.array([]), np.array([])

        # 使用特征工程准备数据
        X, y = self.feature_engineer.prepare_training_data(raw_data)

        logger.info(f"从 {len(raw_data)} 条比赛中提取了 {len(X)} 条训练样本")
        return X, y

    def _compute_odds_baseline(self, y_true, raw_data) -> float:
        """计算赔率隐含概率作为基线的准确率（仅预测热门方）"""
        correct = 0
        total = 0
        for i, (match, true_label) in enumerate(zip(raw_data, y_true)):
            odds = match.get('odds', [])
            if not odds or len(odds) < 3:
                continue
            total += 1
            h, d, a = float(odds[0]), float(odds[1]), float(odds[2])
            # 赔率最小的方向是博彩公司认为最可能的
            min_odds = min(h, d, a)
            if min_odds == h:
                predicted = 0
            elif min_odds == d:
                predicted = 1
            else:
                predicted = 2
            if predicted == true_label:
                correct += 1

        if total > 0:
            return correct / total
        return 0.0

    def train(self, data_path: str = None) -> Dict:
        """
        训练模型

        Args:
            data_path: 训练数据路径（可选，默认从 jczq_results.json 加载）

        Returns:
            训练结果
        """
        logger.info("=" * 50)
        logger.info("开始训练模型...")
        logger.info("=" * 50)

        # 加载数据
        X, y = self._load_training_data(data_path)

        if len(X) < 10:
            logger.warning(f"训练样本不足: {len(X)}")
            return {"error": f"训练样本不足，需要至少10条，当前 {len(X)} 条"}

        n_samples = len(X)

        # ── 先计算赔率基线准确率（在整个数据集上） ──
        raw_data = self._load_real_results()
        odds_baseline = self._compute_odds_baseline(y, raw_data[:len(y)]) if len(raw_data) >= len(y) else None

        # ── 小数据集策略：使用留一交叉验证(LOOCV)评估 ──
        # 对于小数据集，不做train/test split，而是用CV评估
        if n_samples < 100:
            logger.info(f"小数据集模式 ({n_samples} 条)，使用留一交叉验证评估")
            return self._train_small_dataset(X, y, raw_data, odds_baseline)

        # 大数据集：标准训练/测试分割
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=ML_CONFIG.get("train_test_split", 0.2),
            random_state=42,
            stratify=y if len(set(y)) > 1 else None
        )

        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # ── 训练 XGBoost ──
        self._build_model()
        self.model.fit(X_train_scaled, y_train)

        return self._evaluate(X_train_scaled, X_test_scaled, y_train, y_test, raw_data, X, y)

    def _build_model(self):
        """构建模型"""
        if self.model_type == "xgboost":
            self.model = xgb.XGBClassifier(
                n_estimators=300,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=3,
                gamma=0.1,
                reg_alpha=0.5,
                reg_lambda=1.0,
                objective='multi:softmax',
                num_class=3,
                random_state=42,
                use_label_encoder=False,
                eval_metric='mlogloss'
            )
        else:
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(
                n_estimators=300,
                max_depth=8,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )

    def _train_small_dataset(self, X, y, raw_data, odds_baseline) -> Dict:
        """小数据集训练：使用留一交叉验证"""
        from sklearn.model_selection import LeaveOneOut, cross_val_predict
        from sklearn.linear_model import LogisticRegression

        n_samples = len(X)
        result_names = {0: '主胜', 1: '平局', 2: '客胜'}

        # 先标准化全部数据
        X_scaled = self.scaler.fit_transform(X)

        # ── 方法1: 仅用赔率隐含概率预测 (特征0-2) + 逻辑回归 ──
        # 使用前7个特征（赔率相关），避免过拟合
        X_odds = X_scaled[:, :8]  # 赔率相关特征

        # Logistic Regression (更适合小数据集)
        lr_model = LogisticRegression(
            multi_class='multinomial',
            solver='lbfgs',
            max_iter=1000,
            C=1.0,
            random_state=42
        )

        try:
            loo = LeaveOneOut()
            y_pred_lr = cross_val_predict(lr_model, X_odds, y, cv=loo, n_jobs=-1)
            lr_accuracy = accuracy_score(y, y_pred_lr)
        except Exception:
            # 如果LOOCV失败，使用3-fold
            y_pred_lr = cross_val_predict(lr_model, X_odds, y, cv=min(3, n_samples))
            lr_accuracy = accuracy_score(y, y_pred_lr)

        # ── 方法2: XGBoost with shallow depth ──
        xgb_small = xgb.XGBClassifier(
            n_estimators=50,
            max_depth=2,
            learning_rate=0.1,
            subsample=0.9,
            objective='multi:softmax',
            num_class=3,
            random_state=42,
            use_label_encoder=False,
            eval_metric='mlogloss'
        )

        try:
            y_pred_xgb = cross_val_predict(xgb_small, X_odds, y, cv=min(5, n_samples))
            xgb_accuracy = accuracy_score(y, y_pred_xgb)
        except Exception:
            xgb_accuracy = 0.0
            y_pred_xgb = np.zeros(len(y))

        # ── 方法3: 仅用赔率最小方预测（基线对比） ──
        y_pred_odds = np.zeros(len(y), dtype=int)
        for i in range(len(y)):
            # 特征4,5,6 是 home_odds, draw_odds, away_odds
            h_odds = X[i, 4] if X[i, 4] > 0 else 2.5
            d_odds = X[i, 5] if X[i, 5] > 0 else 3.2
            a_odds = X[i, 6] if X[i, 6] > 0 else 2.8
            min_o = min(h_odds, d_odds, a_odds)
            if min_o == h_odds:
                y_pred_odds[i] = 0
            elif min_o == d_odds:
                y_pred_odds[i] = 1
            else:
                y_pred_odds[i] = 2
        odds_acc = accuracy_score(y, y_pred_odds)

        # ── 选择最佳模型用于最终保存 ──
        logger.info(f"LOOCV结果: 逻辑回归={lr_accuracy:.1%}, XGBoost={xgb_accuracy:.1%}, 赔率基线={odds_acc:.1%}")

        # 选择最佳模型
        if lr_accuracy >= xgb_accuracy:
            best_model = lr_model.fit(X_odds, y)
            self.model = best_model
            self.model_type_used = 'logistic_regression'
            used_features = X_odds
            cv_accuracy = lr_accuracy
            y_pred = y_pred_lr
        else:
            best_model = xgb_small.fit(X_odds, y)
            self.model = best_model
            self.model_type_used = 'xgboost_small'
            used_features = X_odds
            cv_accuracy = xgb_accuracy
            y_pred = y_pred_xgb

        # 各类别准确率
        per_class_acc = {}
        for cls, name in result_names.items():
            mask = y == cls
            if mask.sum() > 0:
                per_class_acc[name] = (y_pred[mask] == cls).sum() / mask.sum()

        results = {
            "accuracy": round(cv_accuracy, 4),
            "accuracy_pct": f"{cv_accuracy:.1%}",
            "cv_method": "LOOCV" if n_samples < 50 else f"{min(5, n_samples)}-fold",
            "cv_mean": round(cv_accuracy, 4),
            "cv_std": 0.0,
            "per_class_accuracy": per_class_acc,
            "odds_baseline_accuracy": round(odds_acc, 4),
            "logistic_regression_accuracy": round(lr_accuracy, 4),
            "xgboost_small_accuracy": round(xgb_accuracy, 4),
            "feature_importance": {},
            "model_type_used": self.model_type_used,
            "confusion_matrix": confusion_matrix(y, y_pred).tolist(),
            "classification_report": classification_report(y, y_pred, output_dict=True),
            "total_samples": n_samples,
            "prediction_distribution": {
                "all": dict(zip(*np.unique(y, return_counts=True))),
            },
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"最佳模型 ({self.model_type_used}): LOOCV准确率 {cv_accuracy:.1%}")
        logger.info(f"赔率基线准确率: {odds_acc:.1%}")
        logger.info(f"各类别准确率: {per_class_acc}")

        return results

    def _evaluate(self, X_train, X_test, y_train, y_test, raw_data, X_all, y_all):
        """评估模型（标准流程）"""
        result_names = {0: '主胜', 1: '平局', 2: '客胜'}

        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        # 交叉验证
        try:
            cv = StratifiedKFold(n_splits=min(5, min(np.bincount(y_train))), shuffle=True, random_state=42)
            cv_scores = cross_val_score(self.model, X_train, y_train, cv=cv)
            cv_mean = cv_scores.mean()
            cv_std = cv_scores.std()
        except Exception:
            cv_scores = cross_val_score(self.model, X_train, y_train, cv=3)
            cv_mean = cv_scores.mean()
            cv_std = cv_scores.std()

        # 赔率基线
        odds_baseline = None
        if len(raw_data) >= len(y_all):
            test_start = len(y_train)
            test_raw = raw_data[test_start:test_start + len(y_test)]
            if len(test_raw) == len(y_test):
                odds_baseline = self._compute_odds_baseline(y_test, test_raw)

        # 各类别准确率
        per_class_acc = {}
        for cls, name in result_names.items():
            mask = y_test == cls
            if mask.sum() > 0:
                per_class_acc[name] = (y_pred[mask] == cls).sum() / mask.sum()

        results = {
            "accuracy": round(accuracy, 4),
            "accuracy_pct": f"{accuracy:.1%}",
            "cv_mean": round(cv_mean, 4),
            "cv_std": round(cv_std, 4),
            "per_class_accuracy": per_class_acc,
            "odds_baseline_accuracy": round(odds_baseline, 4) if odds_baseline is not None else None,
            "feature_importance": self.feature_engineer.get_feature_importance(self.model),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "classification_report": classification_report(y_test, y_pred, output_dict=True),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "total_samples": len(X_all),
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"模型训练完成: 准确率 {accuracy:.2%}")
        if odds_baseline is not None:
            logger.info(f"赔率基线: {odds_baseline:.2%}")
        logger.info(f"各类别准确率: {per_class_acc}")

        return results

    def save_model(self, filepath: str):
        """保存模型"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'wb') as f:
            pickle.dump({
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_engineer.FEATURE_NAMES
            }, f)

        logger.info(f"模型已保存: {filepath}")

    def load_model(self, filepath: str):
        """加载模型"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
            self.model = data['model']
            self.scaler = data['scaler']
            if 'feature_names' in data:
                self.feature_engineer.FEATURE_NAMES = data['feature_names']

        logger.info(f"模型已加载: {filepath}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    trainer = ModelTrainer()
    results = trainer.train()

    print("\n" + "=" * 60)
    print("训练结果")
    print("=" * 60)
    print(f"测试集准确率: {results.get('accuracy_pct', 'N/A')}")
    print(f"交叉验证: {results.get('cv_mean', 0):.2%} ± {results.get('cv_std', 0):.2%}")
    if results.get('odds_baseline_accuracy'):
        print(f"赔率基线: {results['odds_baseline_accuracy']:.2%}")
    print(f"\n各类别准确率:")
    for k, v in results.get('per_class_accuracy', {}).items():
        print(f"  {k}: {v:.2%}")
    print(f"\n训练集: {results.get('train_samples', 0)} 样本")
    print(f"测试集: {results.get('test_samples', 0)} 样本")

    # 保存模型
    if results.get('accuracy', 0) > 0:
        model_path = os.path.join(os.path.dirname(__file__), 'models', 'xgboost_model.pkl')
        trainer.save_model(model_path)
        print(f"\n模型已保存: {model_path}")
