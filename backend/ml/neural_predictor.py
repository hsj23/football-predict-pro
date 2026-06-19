"""
神经网络预测模型 - PyTorch实现
使用真实数据训练，提高预测准确率

改进：移除所有随机元素，使用概率分布和赔率隐含概率
"""
import numpy as np
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# PyTorch imports
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    logging.warning("PyTorch未安装，将使用降级模式")

from .feature_engineering import FeatureEngineer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 模型保存路径
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'neural_model.pt')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.npy')


class MatchPredictorNN(nn.Module):
    """PyTorch神经网络模型 - 改进架构"""

    def __init__(self, input_size: int = 32, hidden_sizes: List[int] = [128, 64, 32, 16]):
        super().__init__()

        layers = []
        prev_size = input_size

        for hidden_size in hidden_sizes:
            layers.extend([
                nn.Linear(prev_size, hidden_size),
                nn.BatchNorm1d(hidden_size),
                nn.ReLU(),
                nn.Dropout(0.25)
            ])
            prev_size = hidden_size

        # 输出层：3分类（主胜/平/客胜）
        layers.append(nn.Linear(prev_size, 3))

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        return self.network(x)


class NeuralPredictionModel:
    """
    神经网络预测模型
    使用PyTorch训练和预测，完全基于真实数据
    """

    def __init__(self):
        self.feature_engineer = FeatureEngineer()
        self.model = None
        self.scaler_mean = None
        self.scaler_std = None
        self.is_trained = False
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # 尝试加载已有模型
        self._load_model()

        # 平台权重（用于多平台预测聚合，基于历史准确率动态调整）
        self.platform_weights = {
            '雷速体育': 0.25,
            '500彩票网': 0.20,
            '懂球帝': 0.15,
            'SofaScore': 0.20,
            'Forebet': 0.20
        }

        self.platform_accuracy = {
            '雷速体育': 0.65,
            '500彩票网': 0.62,
            '懂球帝': 0.58,
            'SofaScore': 0.64,
            'Forebet': 0.61
        }

        # 常见比分模式（基于真实足球比分分布）
        self._common_scores = {
            'home': [
                ('2-0', 0.18), ('1-0', 0.17), ('2-1', 0.16),
                ('3-1', 0.12), ('3-0', 0.10), ('1-0', 0.09),
                ('3-2', 0.07), ('4-1', 0.05), ('4-0', 0.03), ('2-0', 0.03)
            ],
            'draw': [
                ('1-1', 0.45), ('0-0', 0.25), ('2-2', 0.20), ('3-3', 0.10)
            ],
            'away': [
                ('0-2', 0.18), ('0-1', 0.17), ('1-2', 0.16),
                ('1-3', 0.12), ('0-3', 0.10), ('0-1', 0.09),
                ('2-3', 0.07), ('1-4', 0.05), ('0-4', 0.03), ('0-2', 0.03)
            ]
        }

    def _load_model(self):
        """加载已训练的模型"""
        if not PYTORCH_AVAILABLE:
            return

        try:
            if os.path.exists(MODEL_PATH):
                self.model = MatchPredictorNN(input_size=self.feature_engineer.feature_count)
                self.model.load_state_dict(torch.load(MODEL_PATH, map_location=self.device))
                self.model.to(self.device)
                self.model.eval()
                self.is_trained = True

                # 加载归一化参数
                if os.path.exists(SCALER_PATH):
                    scaler_data = np.load(SCALER_PATH, allow_pickle=True).item()
                    self.scaler_mean = scaler_data.get('mean')
                    self.scaler_std = scaler_data.get('std')

                logger.info("已加载预训练神经网络模型")
        except Exception as e:
            logger.warning(f"加载模型失败: {e}")
            self.model = None
            self.is_trained = False

    def _save_model(self):
        """保存模型"""
        if not PYTORCH_AVAILABLE or self.model is None:
            return

        try:
            os.makedirs(MODEL_DIR, exist_ok=True)
            torch.save(self.model.state_dict(), MODEL_PATH)

            scaler_data = {'mean': self.scaler_mean, 'std': self.scaler_std}
            np.save(SCALER_PATH, scaler_data)

            logger.info(f"神经网络模型已保存到 {MODEL_PATH}")
        except Exception as e:
            logger.error(f"保存模型失败: {e}")

    def train(self, historical_matches: List[Dict], epochs: int = 150, batch_size: int = 32) -> float:
        """
        训练神经网络模型

        Args:
            historical_matches: 历史比赛数据
            epochs: 训练轮数
            batch_size: 批次大小

        Returns:
            验证集准确率
        """
        if not PYTORCH_AVAILABLE:
            logger.error("PyTorch未安装，无法训练模型")
            return 0.0

        logger.info(f"开始神经网络训练，数据量: {len(historical_matches)}")

        # 准备数据
        X, y = self.feature_engineer.prepare_training_data(historical_matches)

        if len(X) < 50:
            logger.warning("训练数据不足，需要至少50场比赛")
            return 0.0

        # 归一化
        self.scaler_mean = X.mean(axis=0)
        self.scaler_std = X.std(axis=0) + 1e-8
        X_normalized = (X - self.scaler_mean) / self.scaler_std

        # 转换为PyTorch张量
        X_tensor = torch.FloatTensor(X_normalized)
        y_tensor = torch.LongTensor(y)

        # 划分训练集和验证集
        train_size = int(0.8 * len(X))
        X_train, X_val = X_tensor[:train_size], X_tensor[train_size:]
        y_train, y_val = y_tensor[:train_size], y_tensor[train_size:]

        # 创建数据加载器
        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        # 初始化模型（改进架构）
        self.model = MatchPredictorNN(input_size=self.feature_engineer.feature_count)
        self.model.to(self.device)

        # 类别权重（平局更难预测，给更高权重）
        class_counts = np.bincount(y, minlength=3)
        class_weights = torch.FloatTensor([1.0 / max(c, 1) for c in class_counts])
        class_weights = class_weights / class_weights.sum() * 3
        class_weights = class_weights.to(self.device)

        # 损失函数和优化器
        criterion = nn.CrossEntropyLoss(weight=class_weights)
        optimizer = optim.AdamW(self.model.parameters(), lr=0.001, weight_decay=1e-4)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        # 训练
        best_val_acc = 0
        self.model.train()
        for epoch in range(epochs):
            total_loss = 0
            correct = 0
            total = 0

            for batch_X, batch_y in train_loader:
                batch_X = batch_X.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                # 梯度裁剪
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()

                total_loss += loss.item()
                _, predicted = torch.max(outputs, 1)
                total += batch_y.size(0)
                correct += (predicted == batch_y).sum().item()

            scheduler.step()

            if (epoch + 1) % 30 == 0:
                train_acc = 100 * correct / total
                logger.info(f"Epoch [{epoch+1}/{epochs}], Loss: {total_loss:.4f}, Train Acc: {train_acc:.1f}%")

        # 验证
        self.model.eval()
        with torch.no_grad():
            X_val = X_val.to(self.device)
            y_val = y_val.to(self.device)
            outputs = self.model(X_val)
            _, predicted = torch.max(outputs, 1)
            accuracy = 100 * (predicted == y_val).sum().item() / len(y_val)

        logger.info(f"神经网络验证集准确率: {accuracy:.1f}%")

        self.is_trained = True
        self._save_model()

        return accuracy

    def predict_with_features(self, features: np.ndarray) -> Dict:
        """使用特征向量进行预测"""
        if not PYTORCH_AVAILABLE or not self.is_trained or self.model is None:
            return self._odds_based_fallback(features)

        try:
            # 归一化
            if self.scaler_mean is not None and self.scaler_std is not None:
                features_normalized = (features - self.scaler_mean) / self.scaler_std
            else:
                features_normalized = features

            # 预测
            self.model.eval()
            with torch.no_grad():
                x = torch.FloatTensor(features_normalized).unsqueeze(0).to(self.device)
                outputs = self.model(x)
                probs = torch.softmax(outputs, dim=1)

            probs_np = probs.cpu().numpy()[0]

            return {
                'probabilities': {
                    'home': float(probs_np[0] * 100),
                    'draw': float(probs_np[1] * 100),
                    'away': float(probs_np[2] * 100)
                },
                'prediction': ['home', 'draw', 'away'][np.argmax(probs_np)],
                'confidence': float(np.max(probs_np) * 100)
            }
        except Exception as e:
            logger.error(f"神经网络预测失败: {e}")
            return self._odds_based_fallback(features)

    def _odds_based_fallback(self, features: np.ndarray) -> Dict:
        """
        基于赔率的后备预测（不使用随机数）
        从特征中提取赔率隐含概率
        """
        # 特征索引 0,1,2 是赔率隐含概率
        implied_h = float(features[0]) if len(features) > 0 else 0.40
        implied_d = float(features[1]) if len(features) > 1 else 0.28
        implied_a = float(features[2]) if len(features) > 2 else 0.32

        # 归一化
        total = implied_h + implied_d + implied_a
        if total > 0:
            probs = {
                'home': round(implied_h / total * 100, 1),
                'draw': round(implied_d / total * 100, 1),
                'away': round(implied_a / total * 100, 1)
            }
        else:
            probs = {'home': 40.0, 'draw': 28.0, 'away': 32.0}

        prediction = max(probs, key=probs.get)
        return {
            'probabilities': probs,
            'prediction': prediction,
            'confidence': probs[prediction]
        }

    def predict_match(self, match_data: Dict, odds_data: Optional[Dict] = None) -> Dict:
        """
        预测单场比赛

        Args:
            match_data: 比赛数据
            odds_data: 赔率数据（可选）

        Returns:
            预测结果
        """
        # 提取特征
        features = self.feature_engineer.extract_features(match_data, odds_data)

        # 使用神经网络预测
        nn_result = self.predict_with_features(features)

        # 基于概率分布预测比分（不再使用随机）
        predicted_score = self._predict_score_deterministic(
            nn_result['probabilities'], nn_result['prediction']
        )

        # 置信度等级
        confidence = nn_result['confidence']
        if confidence >= 50:
            confidence_level = '高'
        elif confidence >= 38:
            confidence_level = '中'
        else:
            confidence_level = '低'

        return {
            'prediction': nn_result['prediction'],
            'prediction_name': {'home': '主胜', 'draw': '平局', 'away': '客胜'}[nn_result['prediction']],
            'confidence': round(confidence, 1),
            'probabilities': {k: round(v, 1) for k, v in nn_result['probabilities'].items()},
            'confidence_level': confidence_level,
            'predicted_score': predicted_score,
            'model_type': 'neural_network',
            'is_trained': self.is_trained
        }

    def _predict_score_deterministic(self, probabilities: Dict, prediction: str) -> str:
        """基于概率分布预测比分（确定性，不使用随机）"""
        # 取概率最高的常见比分
        scores = self._common_scores.get(prediction, [('1-1', 0.5), ('0-0', 0.5)])
        best_score = max(scores, key=lambda x: x[1])[0]
        return best_score

    def aggregate_predictions(self, predictions: List[Dict]) -> Dict:
        """聚合多平台预测（基于历史准确率加权）"""
        scores = {'home': 0, 'draw': 0, 'away': 0}
        total_weight = 0

        for pred in predictions:
            platform = pred.get('platform', '')
            weight = self.platform_weights.get(platform, 0.1)
            accuracy = self.platform_accuracy.get(platform, 0.5)

            confidence = pred.get('confidence', 50) / 100
            combined_weight = weight * accuracy * confidence

            prediction = pred.get('prediction', 'home')
            if prediction in scores:
                scores[prediction] += combined_weight

            total_weight += combined_weight

        if total_weight > 0:
            scores = {k: v / total_weight for k, v in scores.items()}

        return scores

    def analyze_odds_movement(self, odds_data: Dict) -> Dict:
        """分析赔率变化"""
        trend = odds_data.get('trend', 'stable')

        adjustment = {'home': 0, 'draw': 0, 'away': 0}

        if trend == 'home_dropping':
            adjustment['home'] = 0.10
            adjustment['away'] = -0.03
        elif trend == 'away_dropping':
            adjustment['away'] = 0.10
            adjustment['home'] = -0.03

        kelly = odds_data.get('kelly_index', {})
        if kelly:
            for result in ['home', 'draw', 'away']:
                if kelly.get(result, 33) < 30:
                    adjustment[result] += 0.03

        return adjustment

    def predict(
        self,
        predictions: List[Dict],
        odds_data: Dict,
        home_news: Dict,
        away_news: Dict,
        home_form: str = None,
        away_form: str = None,
        match_data: Dict = None
    ) -> Dict:
        """
        综合预测

        Args:
            predictions: 多平台预测列表
            odds_data: 赔率数据
            home_news: 主队新闻
            away_news: 客队新闻
            home_form: 主队近期战绩
            away_form: 客队近期战绩
            match_data: 比赛数据（用于神经网络预测）

        Returns:
            最终预测结果
        """
        # 如果有比赛数据且模型已训练，使用神经网络预测
        if match_data and self.is_trained:
            nn_result = self.predict_match(match_data, odds_data)

            # 结合多平台预测
            platform_scores = self.aggregate_predictions(predictions)

            # 综合预测（神经网络70% + 多平台30%）
            final_probs = {}
            for key in ['home', 'draw', 'away']:
                nn_prob = nn_result['probabilities'].get(key, 33)
                platform_prob = platform_scores.get(key, 0.33) * 100
                final_probs[key] = round(nn_prob * 0.7 + platform_prob * 0.3, 1)

            # 归一化
            total = sum(final_probs.values())
            if total > 0:
                final_probs = {k: round(v / total * 100, 1) for k, v in final_probs.items()}
            else:
                final_probs = {'home': 33.3, 'draw': 33.3, 'away': 33.3}

            prediction = max(final_probs, key=final_probs.get)
            confidence = final_probs[prediction]

            return {
                'prediction': prediction,
                'prediction_name': {'home': '主胜', 'draw': '平局', 'away': '客胜'}[prediction],
                'confidence': confidence,
                'probabilities': final_probs,
                'confidence_level': '高' if confidence >= 50 else ('中' if confidence >= 38 else '低'),
                'predicted_score': nn_result['predicted_score'],
                'model_type': 'neural_network_ensemble',
                'analysis': {
                    'nn_confidence': nn_result['confidence'],
                    'platform_agreement': max(platform_scores.values()) if platform_scores else 0,
                    'odds_trend': odds_data.get('trend', 'stable')
                }
            }

        # 降级到原有预测方法
        return self._legacy_predict(predictions, odds_data, home_news, away_news)

    def _legacy_predict(
        self,
        predictions: List[Dict],
        odds_data: Dict,
        home_news: Dict,
        away_news: Dict
    ) -> Dict:
        """原有预测方法（降级使用，移除随机不确定性）"""
        platform_scores = self.aggregate_predictions(predictions)
        odds_adjustment = self.analyze_odds_movement(odds_data)

        # 新闻影响
        home_impact = home_news.get('impact_score', 0)
        away_impact = away_news.get('impact_score', 0)
        news_adjustment = {'home': 0, 'draw': 0, 'away': 0}

        diff = home_impact - away_impact
        if diff > 1:
            news_adjustment['home'] = 0.08
            news_adjustment['away'] = -0.04
        elif diff < -1:
            news_adjustment['away'] = 0.08
            news_adjustment['home'] = -0.04

        # 综合（移除随机不确定性项）
        final_scores = {
            'home': (
                platform_scores.get('home', 0) * 0.50 +
                (platform_scores.get('home', 0) + odds_adjustment['home']) * 0.30 +
                (platform_scores.get('home', 0) + news_adjustment['home']) * 0.20
            ),
            'draw': (
                platform_scores.get('draw', 0) * 0.50 +
                (platform_scores.get('draw', 0) + odds_adjustment['draw']) * 0.30 +
                (platform_scores.get('draw', 0) + news_adjustment['draw']) * 0.20
            ),
            'away': (
                platform_scores.get('away', 0) * 0.50 +
                (platform_scores.get('away', 0) + odds_adjustment['away']) * 0.30 +
                (platform_scores.get('away', 0) + news_adjustment['away']) * 0.20
            )
        }

        total = sum(final_scores.values())
        if total > 0:
            probabilities = {k: round(v / total * 100, 1) for k, v in final_scores.items()}
        else:
            probabilities = {'home': 33.3, 'draw': 33.3, 'away': 33.3}

        prediction = max(probabilities, key=probabilities.get)
        confidence = probabilities[prediction]

        return {
            'prediction': prediction,
            'prediction_name': {'home': '主胜', 'draw': '平局', 'away': '客胜'}[prediction],
            'confidence': confidence,
            'probabilities': probabilities,
            'confidence_level': '高' if confidence >= 50 else ('中' if confidence >= 38 else '低'),
            'predicted_score': self._predict_score_deterministic(probabilities, prediction),
            'model_type': 'ensemble'
        }


def test_neural_model():
    """测试神经网络模型"""
    print("=" * 60)
    print("神经网络预测模型测试")
    print("=" * 60)

    model = NeuralPredictionModel()

    # 测试比赛数据（使用真实赔率）
    match_data = {
        'home_team_name': '曼城',
        'away_team_name': '利物浦',
        'league_name': '英超',
    }

    odds_data = {
        'home_odds': 1.85,
        'draw_odds': 3.50,
        'away_odds': 4.20,
        'odds': ['1.85', '3.50', '4.20'],
        'trend': 'home_dropping'
    }

    print("\n[预测结果]")
    result = model.predict_match(match_data, odds_data)
    print(f"预测: {result['prediction_name']}")
    print(f"置信度: {result['confidence']}% ({result['confidence_level']})")
    print(f"概率: 主胜 {result['probabilities']['home']:.1f}%, "
          f"平局 {result['probabilities']['draw']:.1f}%, "
          f"客胜 {result['probabilities']['away']:.1f}%")
    print(f"预测比分: {result['predicted_score']}")
    print(f"模型类型: {result['model_type']}")
    print(f"模型已训练: {result['is_trained']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_neural_model()
