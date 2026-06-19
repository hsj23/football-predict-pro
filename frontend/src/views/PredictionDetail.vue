<template>
  <div class="prediction-detail">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="match-header">
          <div class="match-info" v-if="match">
            <div class="league">{{ match.league_name }}</div>
            <div class="teams">
              <span class="home-team">{{ match.home_team_name }}</span>
              <span class="vs">VS</span>
              <span class="away-team">{{ match.away_team_name }}</span>
            </div>
            <div class="time">{{ formatDateTime(match.match_time) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>综合预测</span>
          </template>
          <div v-if="finalPrediction" class="final-prediction">
            <div class="prediction-result" :class="finalPrediction.prediction">
              {{ getResultText(finalPrediction.prediction) }}
            </div>
            <div class="confidence">
              置信度: {{ finalPrediction.confidence }}%
              <el-tag :type="getConfidenceType(finalPrediction.confidence_level)">
                {{ finalPrediction.confidence_level }}
              </el-tag>
            </div>
            <div class="probabilities">
              <div class="prob-item">
                <span>主胜</span>
                <el-progress :percentage="finalPrediction.probabilities.home" :stroke-width="15" />
              </div>
              <div class="prob-item">
                <span>平局</span>
                <el-progress :percentage="finalPrediction.probabilities.draw" :stroke-width="15" color="#e6a23c" />
              </div>
              <div class="prob-item">
                <span>客胜</span>
                <el-progress :percentage="finalPrediction.probabilities.away" :stroke-width="15" color="#f56c6c" />
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card>
          <template #header>
            <span>平台预测分布</span>
          </template>
          <div v-if="platformAggregation" class="platform-predictions">
            <div class="distribution-chart">
              <div class="bar-container">
                <div class="bar-label">主胜</div>
                <div class="bar-wrapper">
                  <div class="bar home" :style="{ width: platformAggregation.percentages.home + '%' }"></div>
                  <span class="bar-value">{{ platformAggregation.percentages.home }}%</span>
                </div>
              </div>
              <div class="bar-container">
                <div class="bar-label">平局</div>
                <div class="bar-wrapper">
                  <div class="bar draw" :style="{ width: platformAggregation.percentages.draw + '%' }"></div>
                  <span class="bar-value">{{ platformAggregation.percentages.draw }}%</span>
                </div>
              </div>
              <div class="bar-container">
                <div class="bar-label">客胜</div>
                <div class="bar-wrapper">
                  <div class="bar away" :style="{ width: platformAggregation.percentages.away + '%' }"></div>
                  <span class="bar-value">{{ platformAggregation.percentages.away }}%</span>
                </div>
              </div>
            </div>

            <el-table :data="platformAggregation.platform_details" style="margin-top: 20px">
              <el-table-column prop="platform" label="平台" width="120" />
              <el-table-column prop="prediction" label="预测" width="80">
                <template #default="scope">
                  {{ getResultText(scope.row.prediction) }}
                </template>
              </el-table-column>
              <el-table-column prop="confidence" label="置信度" width="100">
                <template #default="scope">
                  {{ scope.row.confidence ? scope.row.confidence + '%' : '-' }}
                </template>
              </el-table-column>
              <el-table-column prop="accuracy" label="历史准确率">
                <template #default="scope">
                  <el-tag v-if="scope.row.accuracy" :type="getAccuracyType(scope.row.accuracy)">
                    {{ scope.row.accuracy }}%
                  </el-tag>
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>赔率分析</span>
          </template>
          <div v-if="oddsAnalysis">
            <el-table :data="oddsAnalysis.opening_odds" size="small">
              <el-table-column prop="bookmaker" label="公司" width="100" />
              <el-table-column prop="home_odds" label="主胜" width="80" />
              <el-table-column prop="draw_odds" label="平局" width="80" />
              <el-table-column prop="away_odds" label="客胜" width="80" />
              <el-table-column prop="tendency" label="倾向">
                <template #default="scope">
                  <el-tag size="small" :type="getTendencyType(scope.row.tendency)">
                    {{ getResultText(scope.row.tendency) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>
            <span>球队状态</span>
          </template>
          <div v-if="teamAnalysis" class="team-form">
            <div v-if="teamAnalysis.home_team" class="team-section">
              <h4>{{ teamAnalysis.home_team.name }} (主)</h4>
              <div class="form-badges">
                <el-tag
                  v-for="(result, index) in teamAnalysis.home_team.recent_form"
                  :key="index"
                  :type="getFormType(result)"
                  size="small"
                  style="margin-right: 5px"
                >
                  {{ result }}
                </el-tag>
              </div>
              <div class="stats">
                胜率: {{ teamAnalysis.home_team.stats.win_rate }}%
              </div>
            </div>
            <div v-if="teamAnalysis.away_team" class="team-section">
              <h4>{{ teamAnalysis.away_team.name }} (客)</h4>
              <div class="form-badges">
                <el-tag
                  v-for="(result, index) in teamAnalysis.away_team.recent_form"
                  :key="index"
                  :type="getFormType(result)"
                  size="small"
                  style="margin-right: 5px"
                >
                  {{ result }}
                </el-tag>
              </div>
              <div class="stats">
                胜率: {{ teamAnalysis.away_team.stats.win_rate }}%
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

export default {
  name: 'PredictionDetail',
  setup() {
    const route = useRoute()
    const matchId = route.params.id
    const match = ref(null)
    const analysis = ref(null)
    const finalPrediction = ref(null)
    const platformAggregation = ref(null)
    const oddsAnalysis = ref(null)
    const teamAnalysis = ref(null)

    const loadAnalysis = async () => {
      try {
        const response = await api.getPredictionAnalysis(matchId)
        analysis.value = response.data
        match.value = response.data.match_info
        finalPrediction.value = response.data.final_prediction
        platformAggregation.value = response.data.predictions?.platform_aggregation
        oddsAnalysis.value = response.data.predictions?.odds_analysis
        teamAnalysis.value = response.data.predictions?.team_analysis
      } catch (error) {
        console.error('加载预测分析失败:', error)
      }
    }

    const formatDateTime = (time) => {
      if (!time) return ''
      const date = new Date(time)
      return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
    }

    const getResultText = (result) => {
      const map = { home: '主胜', draw: '平局', away: '客胜' }
      return map[result] || result
    }

    const getConfidenceType = (level) => {
      const types = { '高': 'success', '中': 'warning', '低': 'danger' }
      return types[level] || 'info'
    }

    const getAccuracyType = (accuracy) => {
      if (accuracy >= 70) return 'success'
      if (accuracy >= 60) return 'warning'
      return 'danger'
    }

    const getTendencyType = (tendency) => {
      const types = { home: 'primary', draw: 'warning', away: 'danger' }
      return types[tendency] || 'info'
    }

    const getFormType = (result) => {
      const types = { W: 'success', D: 'warning', L: 'danger' }
      return types[result] || 'info'
    }

    onMounted(() => {
      loadAnalysis()
    })

    return {
      match,
      analysis,
      finalPrediction,
      platformAggregation,
      oddsAnalysis,
      teamAnalysis,
      formatDateTime,
      getResultText,
      getConfidenceType,
      getAccuracyType,
      getTendencyType,
      getFormType
    }
  }
}
</script>

<style scoped>
.prediction-detail {
  padding: 20px;
}

.match-header {
  text-align: center;
}

.match-info .league {
  color: #909399;
  font-size: 14px;
}

.match-info .teams {
  font-size: 24px;
  font-weight: bold;
  margin: 10px 0;
}

.match-info .home-team {
  color: #409eff;
}

.match-info .away-team {
  color: #f56c6c;
}

.match-info .vs {
  color: #909399;
  margin: 0 20px;
}

.final-prediction .prediction-result {
  font-size: 32px;
  font-weight: bold;
  text-align: center;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 15px;
}

.prediction-result.home {
  background: #ecf5ff;
  color: #409eff;
}

.prediction-result.draw {
  background: #fdf6ec;
  color: #e6a23c;
}

.prediction-result.away {
  background: #fef0f0;
  color: #f56c6c;
}

.confidence {
  text-align: center;
  margin-bottom: 20px;
}

.prob-item {
  margin-bottom: 10px;
}

.bar-container {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.bar-label {
  width: 50px;
}

.bar-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
}

.bar {
  height: 20px;
  border-radius: 4px;
  transition: width 0.3s;
}

.bar.home {
  background: #409eff;
}

.bar.draw {
  background: #e6a23c;
}

.bar.away {
  background: #f56c6c;
}

.bar-value {
  margin-left: 10px;
  width: 50px;
}

.team-section {
  margin-bottom: 20px;
}

.form-badges {
  margin: 10px 0;
}
</style>
