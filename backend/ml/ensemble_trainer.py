"""
集成学习预测器 — XGBoost + CatBoost + LightGBM + Stacking
"""
import os, json, pickle, logging
import numpy as np
from typing import Dict, Tuple, Optional
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')

RESULT_NAMES = {0: 'home', 1: 'draw', 2: 'away'}
RESULT_CN = {'home': '主胜', 'draw': '平局', 'away': '客胜'}


class EnsemblePredictor:
    """三模型 Stacking 集成 + Platt Scaling 校准"""

    def __init__(self):
        self.models = {}        # xgb, cat, lgb
        self.stacker = None     # 逻辑回归 stacking
        self.scaler = StandardScaler()
        self.calibrators = {}   # 每类别的 Platt Scaling 校准器
        self.model_loaded = False
        self._load_all()

    def _load_all(self):
        path = os.path.join(MODEL_DIR, 'ensemble_model.pkl')
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    data = pickle.load(f)
                self.models = data.get('models', {})
                self.stacker = data.get('stacker')
                self.scaler = data.get('scaler', StandardScaler())
                self.model_loaded = True
                logger.info(f"已加载集成模型: {list(self.models.keys())}")
            except Exception as e:
                logger.warning(f"加载集成模型失败: {e}")

    def _build_models(self) -> Dict:
        """构建三个基础模型"""
        models = {
            'xgb': xgb.XGBClassifier(
                n_estimators=300, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                gamma=0.1, reg_alpha=0.5, reg_lambda=1.0,
                objective='multi:softprob', num_class=3,
                random_state=42, use_label_encoder=False, eval_metric='mlogloss'
            ),
        }

        try:
            from catboost import CatBoostClassifier
            models['cat'] = CatBoostClassifier(
                iterations=300, depth=5, learning_rate=0.05,
                l2_leaf_reg=3, random_seed=42,
                verbose=False, allow_writing_files=False,
                loss_function='MultiClass',
            )
        except ImportError:
            logger.warning("CatBoost 未安装，跳过")

        try:
            from lightgbm import LGBMClassifier
            models['lgb'] = LGBMClassifier(
                n_estimators=300, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_samples=20,
                reg_alpha=0.5, reg_lambda=1.0,
                objective='multiclass', num_class=3,
                random_state=42, verbose=-1,
            )
        except ImportError:
            logger.warning("LightGBM 未安装，跳过")

        return models

    def train(self, X: np.ndarray, y: np.ndarray, train_path: str = None) -> Dict:
        """训练集成模型"""
        from sklearn.model_selection import train_test_split

        n = len(X)
        if n < 50:
            return self._train_small(X, y)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
        )

        X_train_s = self.scaler.fit_transform(X_train)
        X_test_s = self.scaler.transform(X_test)

        models = self._build_models()
        if len(models) < 2:
            logger.warning(f"可用模型不足: {len(models)}")

        # 训练各模型
        meta_train = np.zeros((len(X_train), len(models) * 3))
        meta_test = np.zeros((len(X_test), len(models) * 3))

        for i, (name, model) in enumerate(models.items()):
            logger.info(f"  训练 {name}...")
            model.fit(X_train_s, y_train)

            train_probs = model.predict_proba(X_train_s)
            test_probs = model.predict_proba(X_test_s)

            for j in range(3):
                meta_train[:, i * 3 + j] = train_probs[:, j]
                meta_test[:, i * 3 + j] = test_probs[:, j]

        # Stacking: 逻辑回归学习各模型权重
        self.stacker = LogisticRegression(
            multi_class='multinomial', solver='lbfgs',
            max_iter=1000, C=0.5, random_state=42
        )
        self.stacker.fit(meta_train, y_train)

        # 评估
        y_pred = self.stacker.predict(meta_test)
        accuracy = accuracy_score(y_test, y_pred)

        # 各模型单独准确率
        individual_acc = {}
        for name, model in models.items():
            pred = model.predict(X_test_s)
            individual_acc[name] = accuracy_score(y_test, pred)

        # 各类别准确率
        per_class = {}
        for cls, cn in RESULT_CN.items():
            idx = list(RESULT_CN.keys()).index(cls)
            mask = y_test == idx
            if mask.sum() > 0:
                per_class[cn] = (y_pred[mask] == idx).sum() / mask.sum()

        # Platt Scaling 概率校准
        from sklearn.calibration import CalibratedClassifierCV
        for name, model in models.items():
            try:
                cal = CalibratedClassifierCV(model, method='sigmoid', cv=3)
                cal.fit(X_train_s, y_train)
                models[name] = cal
            except Exception:
                pass  # 校准失败则使用原始模型

        self.models = models
        self.model_loaded = True

        results = {
            'accuracy': round(accuracy, 4),
            'accuracy_pct': f'{accuracy:.1%}',
            'individual_accuracy': individual_acc,
            'per_class_accuracy': per_class,
            'models_used': list(models.keys()),
            'train_samples': len(X_train),
            'test_samples': len(X_test),
            'confusion_matrix': confusion_matrix(y_test, y_pred).tolist(),
            'classification_report': classification_report(y_test, y_pred, output_dict=True),
        }

        logger.info(f"集成准确率: {accuracy:.1%} (单模型: {individual_acc})")
        logger.info(f"各类别: {per_class}")

        return results

    def _train_small(self, X, y):
        """小数据集: 只用 XGBoost"""
        X_s = self.scaler.fit_transform(X)
        from sklearn.model_selection import cross_val_predict, LeaveOneOut

        model = xgb.XGBClassifier(
            n_estimators=50, max_depth=2, learning_rate=0.1,
            objective='multi:softmax', num_class=3,
            random_state=42, use_label_encoder=False, eval_metric='mlogloss'
        )

        cv = LeaveOneOut() if len(X) < 30 else min(5, len(X))
        y_pred = cross_val_predict(model, X_s, y, cv=cv, n_jobs=-1)
        accuracy = accuracy_score(y, y_pred)

        model.fit(X_s, y)
        self.models = {'xgb': model}
        self.stacker = None
        self.model_loaded = True

        per_class = {}
        for cls, cn in RESULT_CN.items():
            idx = list(RESULT_CN.keys()).index(cls)
            mask = y == idx
            if mask.sum() > 0:
                per_class[cn] = (y_pred[mask] == idx).sum() / mask.sum()

        logger.info(f"小数据集集成: {accuracy:.1%}")
        return {'accuracy': round(accuracy, 4), 'accuracy_pct': f'{accuracy:.1%}',
                'per_class_accuracy': per_class, 'models_used': ['xgb'],
                'total_samples': len(X)}

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """返回 [home, draw, away] 概率"""
        if not self.model_loaded or not self.models:
            return np.array([0.40, 0.30, 0.30])

        features = features.reshape(1, -1)
        try:
            features_s = self.scaler.transform(features)
        except Exception:
            return np.array([0.40, 0.30, 0.30])

        if self.stacker and len(self.models) >= 2:
            meta = np.zeros((1, len(self.models) * 3))
            for i, (name, model) in enumerate(self.models.items()):
                probs = model.predict_proba(features_s)
                for j in range(3):
                    meta[0, i * 3 + j] = probs[0, j]
            probs = self.stacker.predict_proba(meta)[0]
        else:
            # 单模型或退化
            model = list(self.models.values())[0]
            probs = model.predict_proba(features_s)[0]

        return np.array([float(probs[0]), float(probs[1]), float(probs[2])])

    def save(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        path = os.path.join(MODEL_DIR, 'ensemble_model.pkl')
        with open(path, 'wb') as f:
            pickle.dump({
                'models': self.models,
                'stacker': self.stacker,
                'scaler': self.scaler,
            }, f)
        logger.info(f"集成模型已保存: {path}")

    def train_and_save(self, data_path: str = None):
        """从训练数据加载、训练并保存"""
        from ml.feature_engineering import FeatureEngineer

        if data_path is None:
            data_path = os.path.join(DATA_DIR, 'training_data.json')

        if not os.path.exists(data_path):
            logger.error(f"训练数据不存在: {data_path}")
            return None

        with open(data_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            raw = raw.get('matches', raw.get('results', []))

        fe = FeatureEngineer()
        X, y = fe.prepare_training_data(raw)

        logger.info(f"准备 {len(X)} 条训练样本用于集成模型")
        results = self.train(X, y)
        self.save()
        return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    ep = EnsemblePredictor()
    results = ep.train_and_save()
    if results:
        print(f"\n集成准确率: {results['accuracy_pct']}")
        print(f"单模型: {results['individual_accuracy']}")
        print(f"各类别: {results['per_class_accuracy']}")
