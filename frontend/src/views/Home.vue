<template>
  <div class="home">
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card class="welcome-card">
          <h1>FootballPredict Pro</h1>
          <p>智能足彩预测分析系统</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="4">
        <el-card class="stat-card">
          <div class="stat-number">{{ stats.matches.today }}</div>
          <div class="stat-label">今日比赛</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card">
          <div class="stat-number">{{ stats.predictions.total }}</div>
          <div class="stat-label">总预测数</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card success">
          <div class="stat-number" style="color: #67c23a">{{ stats.predictions.correct || 0 }}</div>
          <div class="stat-label">预测正确</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card">
          <div class="stat-number" style="color: #f56c6c">{{ stats.predictions.wrong || 0 }}</div>
          <div class="stat-label">预测错误</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card success">
          <div class="stat-number">{{ stats.predictions.accuracy_rate }}%</div>
          <div class="stat-label">准确率</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card">
          <div class="stat-number" style="color: #e6a23c">{{ stats.predictions.recent_7d_accuracy || 0 }}%</div>
          <div class="stat-label">近7天准确率</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="16">
        <el-card>
          <template #header>
            <span>今日比赛</span>
            <el-button type="primary" size="small" style="float: right" @click="goToMatches">
              查看全部
            </el-button>
          </template>
          <el-table :data="todayMatches" style="width: 100%">
            <el-table-column prop="league_name" label="联赛" width="120" />
            <el-table-column prop="match_time" label="时间" width="100">
              <template #default="scope">
                {{ formatTime(scope.row.match_time) }}
              </template>
            </el-table-column>
            <el-table-column label="主队">
              <template #default="scope">
                <router-link :to="'/team/' + encodeURIComponent(scope.row.home_team_name)" class="team-link home">
                  {{ scope.row.home_team_name }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column label="比分" width="80" align="center">
              <template #default="scope">
                <span v-if="scope.row.status === 'finished'">
                  {{ scope.row.home_score }} - {{ scope.row.away_score }}
                </span>
                <span v-else>VS</span>
              </template>
            </el-table-column>
            <el-table-column label="客队">
              <template #default="scope">
                <router-link :to="'/team/' + encodeURIComponent(scope.row.away_team_name)" class="team-link away">
                  {{ scope.row.away_team_name }}
                </router-link>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="scope">
                <el-button size="small" @click="viewPrediction(scope.row)">预测</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>热门预测</span>
          </template>
          <div v-for="match in hotMatches" :key="match.match_id" class="hot-match">
            <div class="match-info">
              <div class="teams">{{ match.home_team_name }} vs {{ match.away_team_name }}</div>
              <div class="prediction-count">{{ match.prediction_count }} 个预测</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

export default {
  name: 'Home',
  setup() {
    const router = useRouter()
    const stats = ref({
      matches: { total: 0, today: 0 },
      predictions: { total: 0, accuracy_rate: 0, correct: 0, wrong: 0, recent_7d_accuracy: 0 },
      teams: { total: 0 }
    })
    const todayMatches = ref([])
    const hotMatches = ref([])

    const loadStats = async () => {
      try {
        const response = await api.getStatistics()
        const data = response.data
        stats.value = {
          matches: data.matches || { total: 0, today: 0 },
          predictions: data.predictions || { total: 0, accuracy_rate: 0, correct: 0, wrong: 0, recent_7d_accuracy: 0 },
          teams: data.teams || { total: 0 }
        }
      } catch (error) {
        console.error('加载统计失败:', error)
      }
    }

    const loadTodayMatches = async () => {
      try {
        const response = await api.getTodayMatches()
        todayMatches.value = response.data.matches.slice(0, 5)
      } catch (error) {
        console.error('加载今日比赛失败:', error)
      }
    }

    const loadHotMatches = async () => {
      try {
        const response = await api.getHotMatches()
        hotMatches.value = response.data.hot_matches.slice(0, 5)
      } catch (error) {
        console.error('加载热门比赛失败:', error)
      }
    }

    const formatTime = (time) => {
      if (!time) return ''
      const date = new Date(time)
      return `${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
    }

    const goToMatches = () => {
      router.push('/matches')
    }

    const viewPrediction = (match) => {
      router.push(`/prediction/${match.match_id}`)
    }

    onMounted(() => {
      loadStats()
      loadTodayMatches()
      loadHotMatches()
    })

    return {
      stats,
      todayMatches,
      hotMatches,
      formatTime,
      goToMatches,
      viewPrediction
    }
  }
}
</script>

<style scoped>
.home {
  padding: 20px;
}

.welcome-card {
  text-align: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.welcome-card h1 {
  margin: 0;
  font-size: 28px;
}

.welcome-card p {
  margin: 10px 0 0;
  opacity: 0.9;
}

.stat-card {
  text-align: center;
  padding: 20px;
}

.stat-number {
  font-size: 36px;
  font-weight: bold;
  color: #409eff;
}

.stat-card.success .stat-number {
  color: #67c23a;
}

.stat-label {
  margin-top: 10px;
  color: #909399;
}

.team-link {
  text-decoration: none;
  font-weight: bold;
  cursor: pointer;
}

.team-link:hover {
  text-decoration: underline;
}

.team-link.home {
  color: #409eff;
}

.team-link.away {
  color: #f56c6c;
}

.hot-match {
  padding: 15px;
  border-bottom: 1px solid #eee;
}

.hot-match:last-child {
  border-bottom: none;
}

.match-info .teams {
  font-weight: bold;
  margin-bottom: 5px;
}

.prediction-count {
  font-size: 12px;
  color: #909399;
}
</style>
