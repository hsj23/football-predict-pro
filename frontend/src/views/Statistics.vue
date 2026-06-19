<template>
  <div class="statistics-page">
    <!-- 筛选栏 -->
    <el-card class="filter-card">
      <div class="filter-row">
        <div class="filter-left">
          <el-date-picker
            v-model="selectedDate"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="onDateChange"
            style="width: 180px"
          />
          <el-select
            v-model="selectedLeague"
            placeholder="联赛筛选"
            clearable
            filterable
            @change="loadAll"
            style="width: 180px"
          >
            <el-option
              v-for="lg in allLeagues"
              :key="lg"
              :label="lg"
              :value="lg"
            />
          </el-select>
          <el-input
            v-model="teamFilter"
            placeholder="队伍筛选（输入队名）"
            clearable
            @change="loadAll"
            style="width: 220px"
          />
          <el-select
            v-model="predictionFilter"
            placeholder="预测结果筛选"
            clearable
            @change="loadAll"
            style="width: 160px"
          >
            <el-option label="主胜" value="home" />
            <el-option label="平局" value="draw" />
            <el-option label="客胜" value="away" />
          </el-select>
        </div>
        <div class="filter-right">
          <el-button type="primary" :loading="refreshing" @click="refreshData">
            <el-icon v-if="!refreshing"><Refresh /></el-icon>
            刷新数据
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 统计概览卡片 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="4">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value today">{{ summary.todayMatches }}</div>
          <div class="stat-label">今日比赛</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value">{{ summary.totalPredictions }}</div>
          <div class="stat-label">总预测数</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card correct" shadow="hover">
          <div class="stat-value correct">{{ summary.correct }}</div>
          <div class="stat-label">预测正确</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card wrong" shadow="hover">
          <div class="stat-value wrong">{{ summary.wrong }}</div>
          <div class="stat-label">预测错误</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value accuracy">{{ summary.accuracy }}%</div>
          <div class="stat-label">准确率</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card class="stat-card" shadow="hover">
          <div class="stat-value recent">{{ summary.recent7d }}%</div>
          <div class="stat-label">近7天准确率</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 预测类型分布 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="8">
        <el-card class="type-card home" shadow="hover">
          <div class="type-content">
            <div class="type-value">{{ predictionTypeStats.home }}</div>
            <div class="type-label">预测主胜</div>
            <div class="type-sub">占比 {{ predictionTypeStats.homePercent }}%</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="type-card draw" shadow="hover">
          <div class="type-content">
            <div class="type-value">{{ predictionTypeStats.draw }}</div>
            <div class="type-label">预测平局</div>
            <div class="type-sub">占比 {{ predictionTypeStats.drawPercent }}%</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="type-card away" shadow="hover">
          <div class="type-content">
            <div class="type-value">{{ predictionTypeStats.away }}</div>
            <div class="type-label">预测客胜</div>
            <div class="type-sub">占比 {{ predictionTypeStats.awayPercent }}%</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 联赛准确率 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <span>各联赛预测统计</span>
      </template>
      <div class="league-stats-grid">
        <div
          v-for="lg in leagueStats"
          :key="lg.league"
          class="league-stat-item"
        >
          <div class="league-name">{{ lg.league }}</div>
          <el-progress
            :percentage="lg.accuracy"
            :stroke-width="8"
            :color="lg.accuracy >= 60 ? '#67c23a' : lg.accuracy >= 45 ? '#e6a23c' : '#f56c6c'"
          />
          <div class="league-detail">{{ lg.correct }}/{{ lg.total }} · {{ lg.accuracy }}%</div>
        </div>
        <div v-if="!leagueStats.length" class="empty-hint">暂无联赛统计数据</div>
      </div>
    </el-card>

    <!-- 预测列表 -->
    <el-card style="margin-top: 16px">
      <template #header>
        <div class="table-header">
          <span>预测列表（{{ selectedDate }}）</span>
          <el-tag type="info" size="small">共 {{ predictionList.length }} 条</el-tag>
        </div>
      </template>

      <el-table
        :data="predictionList"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="showPredictionDetail"
      >
        <el-table-column prop="league" label="联赛" width="110">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.league }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="主队" width="140">
          <template #default="{ row }">
            <el-link
              type="primary"
              :underline="false"
              @click.stop="goToTeam(row.home_team)"
            >{{ row.home_team }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="比分" width="90" align="center">
          <template #default="{ row }">
            <span v-if="row.actual_score" class="score-text">{{ row.actual_score }}</span>
            <span v-else class="vs-text">VS</span>
          </template>
        </el-table-column>
        <el-table-column label="客队" width="140">
          <template #default="{ row }">
            <el-link
              type="danger"
              :underline="false"
              @click.stop="goToTeam(row.away_team)"
            >{{ row.away_team }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="预测" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              :type="getPredictionTagType(row.prediction_result)"
              size="small"
            >{{ getPredictionName(row.prediction_result) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="85" align="center">
          <template #default="{ row }">
            <span :style="{ color: getConfidenceColor(row.confidence) }">
              {{ row.confidence ? Math.round(row.confidence) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="实际结果" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.actual_result"
              :type="row.is_correct === 1 ? 'success' : row.is_correct === 2 ? 'danger' : 'info'"
              size="small"
            >{{ getPredictionName(row.actual_result) }}</el-tag>
            <span v-else class="pending-text">待定</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_correct === 1" type="success" size="small">正确</el-tag>
            <el-tag v-else-if="row.is_correct === 2" type="danger" size="small">错误</el-tag>
            <el-tag v-else type="warning" size="small">待验证</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="110">
          <template #default="{ row }">
            {{ formatDate(row.match_date) }}
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadPredictionList"
        style="margin-top: 16px; justify-content: flex-end"
      />
    </el-card>

    <!-- 预测详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      title="预测详情"
      width="700px"
      destroy-on-close
    >
      <div v-if="currentDetail" class="detail-body">
        <div class="detail-match-header">
          <h3>{{ currentDetail.league_name || currentDetail.league }}</h3>
          <div class="teams-big">
            <span class="home-name">{{ currentDetail.home_team_name || currentDetail.home_team }}</span>
            <span class="vs-big">
              <template v-if="currentDetail.actual_score">{{ currentDetail.actual_score }}</template>
              <template v-else>VS</template>
            </span>
            <span class="away-name">{{ currentDetail.away_team_name || currentDetail.away_team }}</span>
          </div>
          <p class="match-time">{{ currentDetail.match_time || currentDetail.match_date }}</p>
        </div>

        <el-divider />

        <div v-if="currentDetail.prediction" class="detail-section">
          <h4>预测结果</h4>
          <div class="pred-big" :class="currentDetail.prediction.prediction">
            {{ currentDetail.prediction.prediction_name }}
            <span class="conf-sub">(置信度 {{ currentDetail.prediction.confidence }}%)</span>
          </div>
          <div class="prob-row">
            <span>主胜 {{ currentDetail.prediction.probabilities?.home || 0 }}%</span>
            <span>平局 {{ currentDetail.prediction.probabilities?.draw || 0 }}%</span>
            <span>客胜 {{ currentDetail.prediction.probabilities?.away || 0 }}%</span>
          </div>
        </div>

        <el-divider v-if="currentDetail.analysis_summary && currentDetail.analysis_summary.length" />

        <div v-if="currentDetail.analysis_summary && currentDetail.analysis_summary.length" class="detail-section">
          <h4>分析理由</h4>
          <ul class="reason-list">
            <li v-for="(s, idx) in currentDetail.analysis_summary" :key="idx">{{ s }}</li>
          </ul>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { ref, reactive, onMounted, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '../api'

export default {
  name: 'Statistics',
  components: { Refresh },
  setup() {
    const router = useRouter()
    const loading = ref(false)
    const refreshing = ref(false)
    const selectedDate = ref(getTodayStr())
    const selectedLeague = ref('')
    const teamFilter = ref('')
    const predictionFilter = ref('')
    const page = ref(1)
    const pageSize = ref(20)
    const total = ref(0)
    const predictionList = ref([])
    const detailVisible = ref(false)
    const currentDetail = ref(null)

    const allLeagues = ref([
      '英超', '西甲', '德甲', '意甲', '法甲',
      '中超', '欧冠', '欧联杯', '日职', '韩K联',
      '澳超', '荷甲', '葡超', '巴甲', '阿甲',
      '英冠', '德乙', '法乙', '国际赛'
    ])

    const summary = reactive({
      todayMatches: 0,
      totalPredictions: 0,
      correct: 0,
      wrong: 0,
      accuracy: 0,
      recent7d: 0
    })

    const predictionTypeStats = reactive({
      home: 0,
      draw: 0,
      away: 0,
      homePercent: 0,
      drawPercent: 0,
      awayPercent: 0
    })

    const leagueStats = ref([])

    function getTodayStr() {
      const d = new Date()
      return d.toISOString().split('T')[0]
    }

    function getTomorrowStr() {
      const d = new Date()
      d.setDate(d.getDate() + 1)
      return d.toISOString().split('T')[0]
    }

    async function loadStats() {
      try {
        const startDate = selectedDate.value
        const endDate = selectedDate.value
        const res = await api.getHistoryStatistics()
        if (res.data && res.data.summary) {
          const s = res.data.summary
          summary.totalPredictions = s.total || 0
          summary.correct = s.correct || 0
          summary.wrong = s.wrong || 0
          summary.accuracy = s.accuracy || 0
          summary.recent7d = s.recent_7_days_accuracy || 0
        }

        // Prediction type stats
        if (res.data && res.data.prediction_type_accuracy) {
          res.data.prediction_type_accuracy.forEach(t => {
            predictionTypeStats[t.type] = t.total || 0
          })
          const total = predictionTypeStats.home + predictionTypeStats.draw + predictionTypeStats.away
          if (total > 0) {
            predictionTypeStats.homePercent = Math.round(predictionTypeStats.home / total * 100)
            predictionTypeStats.drawPercent = Math.round(predictionTypeStats.draw / total * 100)
            predictionTypeStats.awayPercent = Math.round(predictionTypeStats.away / total * 100)
          }
        }

        // League stats
        if (res.data && res.data.league_accuracy) {
          leagueStats.value = res.data.league_accuracy.slice(0, 16)
        }

        // Also load today's matches count
        await loadTodayMatchCount()
      } catch (e) {
        console.error('加载统计数据失败:', e)
      }
    }

    async function loadTodayMatchCount() {
      try {
        const res = await api.getMatches({
          date: selectedDate.value,
          limit: 1
        })
        summary.todayMatches = res.data?.total || 0
      } catch (e) {
        // If matches endpoint doesn't support date param, try today's matches
        try {
          const res = await api.getTodayMatches()
          summary.todayMatches = res.data?.count || 0
        } catch (e2) {
          summary.todayMatches = 0
        }
      }
    }

    async function loadPredictionList() {
      loading.value = true
      try {
        const params = {
          page: page.value,
          page_size: pageSize.value
        }

        if (selectedDate.value) {
          params.start_date = selectedDate.value
          params.end_date = selectedDate.value
        }
        if (selectedLeague.value) {
          params.league = selectedLeague.value
        }
        if (teamFilter.value) {
          params.team = teamFilter.value
        }
        if (predictionFilter.value) {
          params.result = 'correct'  // We handle this differently
        }

        const res = await api.getHistoryList(params)
        if (res.data) {
          let records = res.data.records || []
          // Client-side prediction type filter
          if (predictionFilter.value) {
            records = records.filter(r => r.prediction_result === predictionFilter.value)
          }
          predictionList.value = records
          total.value = res.data.total || records.length
        }
      } catch (e) {
        console.error('加载预测列表失败:', e)
        predictionList.value = []
        total.value = 0
      } finally {
        loading.value = false
      }
    }

    async function loadAll() {
      page.value = 1
      await Promise.all([loadStats(), loadPredictionList()])
    }

    function onDateChange() {
      loadAll()
    }

    async function refreshData() {
      refreshing.value = true
      try {
        await api.refreshTodayData()
        await loadAll()
        ElMessage.success('数据刷新完成')
      } catch (e) {
        console.warn('刷新今日数据失败，尝试批量预测...')
        try {
          await api.batchPredict()
          await loadAll()
          ElMessage.success('预测数据已更新')
        } catch (e2) {
          console.error('刷新失败:', e2)
          ElMessage.error('刷新失败，请检查后端服务')
        }
      } finally {
        refreshing.value = false
      }
    }

    // Auto-refresh: check if there are upcoming matches that need prediction
    let autoRefreshTimer = null

    function startAutoRefresh() {
      stopAutoRefresh()
      autoRefreshTimer = setInterval(() => {
        loadStats()
      }, 60000) // Refresh stats every 60 seconds
    }

    function stopAutoRefresh() {
      if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer)
        autoRefreshTimer = null
      }
    }

    async function showPredictionDetail(row) {
      try {
        const res = await api.getHistoryDetail(row.match_id)
        currentDetail.value = res.data
        detailVisible.value = true
      } catch (e) {
        console.error('加载详情失败:', e)
        ElMessage.warning('加载详情失败')
      }
    }

    function goToTeam(teamName) {
      if (teamName) {
        router.push(`/team/${encodeURIComponent(teamName)}`)
      }
    }

    function getPredictionName(result) {
      const map = { home: '主胜', draw: '平局', away: '客胜' }
      return map[result] || result || '-'
    }

    function getPredictionTagType(result) {
      const map = { home: '', draw: 'warning', away: 'danger' }
      return map[result] || 'info'
    }

    function getConfidenceColor(confidence) {
      if (!confidence) return '#909399'
      const c = Math.round(confidence)
      if (c >= 55) return '#67c23a'
      if (c >= 40) return '#e6a23c'
      return '#f56c6c'
    }

    function formatDate(dateStr) {
      if (!dateStr) return '-'
      return String(dateStr).slice(0, 10)
    }

    onMounted(() => {
      loadAll()
      startAutoRefresh()
    })

    onUnmounted(() => {
      stopAutoRefresh()
    })

    return {
      loading,
      refreshing,
      selectedDate,
      selectedLeague,
      teamFilter,
      predictionFilter,
      page,
      pageSize,
      total,
      predictionList,
      allLeagues,
      summary,
      predictionTypeStats,
      leagueStats,
      detailVisible,
      currentDetail,
      onDateChange,
      loadAll,
      refreshData,
      showPredictionDetail,
      goToTeam,
      getPredictionName,
      getPredictionTagType,
      getConfidenceColor,
      formatDate
    }
  }
}
</script>

<style scoped>
.statistics-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.filter-card {
  margin-bottom: 0;
}

.filter-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-left {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.stat-card {
  text-align: center;
  padding: 8px 0;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #409eff;
}

.stat-value.today { color: #409eff; }
.stat-value.correct { color: #67c23a; }
.stat-value.wrong { color: #f56c6c; }
.stat-value.accuracy { color: #409eff; }
.stat-value.recent { color: #e6a23c; }

.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}

.type-card {
  text-align: center;
}

.type-card.home { border-top: 3px solid #409eff; }
.type-card.draw { border-top: 3px solid #e6a23c; }
.type-card.away { border-top: 3px solid #f56c6c; }

.type-value {
  font-size: 32px;
  font-weight: bold;
}

.type-card.home .type-value { color: #409eff; }
.type-card.draw .type-value { color: #e6a23c; }
.type-card.away .type-value { color: #f56c6c; }

.type-label {
  font-size: 14px;
  color: #303133;
  margin-top: 4px;
}

.type-sub {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.league-stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.league-stat-item {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.league-name {
  font-weight: bold;
  margin-bottom: 8px;
  font-size: 14px;
}

.league-detail {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}

.empty-hint {
  grid-column: 1 / -1;
  text-align: center;
  color: #909399;
  padding: 20px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.score-text {
  font-weight: bold;
  font-size: 15px;
}

.vs-text {
  color: #c0c4cc;
}

.pending-text {
  color: #c0c4cc;
}

.detail-body {
  padding: 4px 0;
}

.detail-match-header {
  text-align: center;
}

.detail-match-header h3 {
  color: #909399;
  font-size: 14px;
  margin-bottom: 10px;
}

.teams-big {
  font-size: 22px;
  font-weight: bold;
  margin-bottom: 8px;
}

.home-name { color: #409eff; }
.away-name { color: #f56c6c; }
.vs-big {
  margin: 0 16px;
  color: #909399;
}

.match-time {
  color: #909399;
  font-size: 13px;
}

.pred-big {
  font-size: 24px;
  font-weight: bold;
  text-align: center;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.pred-big.home { background: #ecf5ff; color: #409eff; }
.pred-big.draw { background: #fdf6ec; color: #e6a23c; }
.pred-big.away { background: #fef0f0; color: #f56c6c; }

.conf-sub {
  font-size: 14px;
  font-weight: normal;
  color: #909399;
  margin-left: 8px;
}

.prob-row {
  display: flex;
  gap: 24px;
  justify-content: center;
  color: #606266;
  font-size: 14px;
}

.reason-list {
  margin: 0;
  padding-left: 20px;
}

.reason-list li {
  margin-bottom: 6px;
  color: #606266;
  line-height: 1.6;
}

.detail-section {
  margin-bottom: 6px;
}

.detail-section h4 {
  margin-bottom: 10px;
  color: #303133;
}
</style>
