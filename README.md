# FootballPredict Pro - 智能足彩预测分析系统

## 项目简介

FootballPredict Pro 是一个专业的足球比赛预测分析系统，通过整合多平台预测数据、实时赔率、球队状态等信息，运用统计学和机器学习方法，为用户提供科学的比赛预测参考。

## 功能特点

- **多平台预测聚合**：整合雷速体育、500彩票网等平台预测
- **赔率分析引擎**：凯利指数计算、赔率异动监控、历史赔率对比
- **球队状态分析**：近期战绩、交锋历史、伤病信息
- **机器学习预测**：基于XGBoost的预测模型
- **可视化展示**：直观的图表和数据呈现
- **准确率追踪**：历史预测准确率统计

## 项目结构

```
FootballPredictPro/
├── backend/                 # 后端服务 (FastAPI + Python)
│   ├── app/                 # 应用核心
│   │   ├── api/             # API路由
│   │   ├── models/          # 数据模型
│   │   ├── services/        # 业务逻辑
│   │   └── utils/           # 工具函数
│   ├── crawlers/            # 爬虫模块
│   ├── ml/                  # 机器学习模块
│   ├── tasks/               # 定时任务
│   └── requirements.txt
├── frontend/                # 前端项目 (Vue 3)
│   ├── src/
│   │   ├── views/           # 页面组件
│   │   ├── components/      # 公共组件
│   │   └── api/             # API调用
│   └── package.json
├── data/                    # 数据目录
└── docs/                    # 文档
```

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+
- MySQL 8.0+
- Redis (可选)

### 后端安装

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置数据库
# 修改 app/config.py 中的 DATABASE_URL

# 启动服务
python -m app.main
```

### 前端安装

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 访问系统

- 前端地址：http://localhost:5173
- API文档：http://localhost:8000/docs

## API 接口

### 比赛接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/matches | 获取比赛列表 |
| GET | /api/matches/today/list | 获取今日比赛 |
| GET | /api/matches/{match_id} | 获取比赛详情 |

### 预测接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/predictions/{match_id} | 获取比赛预测 |
| GET | /api/predictions/{match_id}/analysis | 获取综合预测分析 |
| GET | /api/predictions/platforms/accuracy | 获取平台准确率 |

### 赔率接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/odds/{match_id} | 获取比赛赔率 |
| GET | /api/odds/{match_id}/analysis | 获取赔率分析 |
| GET | /api/odds/{match_id}/kelly | 获取凯利指数 |

## 定时任务

系统包含以下定时任务：

- 每30分钟更新赔率数据
- 每1小时更新预测数据
- 每天6:00更新比赛列表
- 每周训练一次机器学习模型

## 数据来源

- 雷速体育 (leisu.com)
- 500彩票网 (500.com)
- FlashScore (flashscore.com)
- API-Football

## 注意事项

⚠️ **重要声明**

本项目仅供学习和研究使用，所有预测分析结果仅供参考，不构成任何投注建议。博彩有风险，参与需谨慎。

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提交 Issue。
