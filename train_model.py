import sys
import os
sys.path.insert(0, 'D:/小黄的助手/足彩预测系统/backend')

from ml.model_trainer import ModelTrainer

trainer = ModelTrainer()

# 训练模型
print('开始训练模型...')
result = trainer.train()
print(f'训练完成，模型类型: {result.get("model_type_used", "unknown")}')

# 保存模型
model_dir = 'D:/小黄的助手/足彩预测系统/backend/ml/models'
os.makedirs(model_dir, exist_ok=True)
model_path = os.path.join(model_dir, 'xgboost_model.pkl')
trainer.save_model(model_path)
print(f'模型已保存到: {model_path}')
print(f'模型文件存在: {os.path.exists(model_path)}')
