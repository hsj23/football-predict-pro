<template>
  <div class="team-history">
    <el-card class="team-header">
      <div class="header-info">
        <h1>{{ teamName }}</h1>
        <div class="stats-row">
          <el-tag size="large" type="info">共 {{ total }} 场比赛</el-tag>
          <el-tag size="large" type="success">预测正确 {{ stats.correct }} 场</el-tag>
          <el-tag size="large" type="danger">预测错误 {{ stats.wrong }} 场</el-tag>
          <el-tag size="large" :type="accuracyType">准确率 {{ accuracyRate }}%</el-tag>
        </div>
      </div>
    </el-card>

    <el-card style="margin-top: 20px">
      <template #header>
        <span>历史比赛记录</span>
        <el-button size="small" style="float: right" @click="goBack">返回</el-button>
      </template>

      <el-table :data="records" v-loading="loading" style="width: 100%" row-key="id" @row-click="showDetail">
        <el-table-column prop="match_date" label="日期" width="120" />
        <el-table-column prop="league" label="联赛" width="120">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.league }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="主队" width="140">
          <template #default="scope">
            <span :class="scope.row.home_team === teamName ? 'is-team' : ''">{{ scope.row.home_team }}</span>
          </template>
        </el-table-column>
        <el-table-column label="比分" width="80" align="center">
          <template #default="scope">
            <span v-if="scope.row.actual_score" class="score">{{ scope.row.actual_score }}</span>
            <span v-else class="pending">-</span>
          </template>
        </el-table-column>
        <el-table-column label="客队" width="140">
          <template #default="scope">
            <span :class="scope.row.away_team === teamName ? 'is-team' : ''">{{ scope.row.away_team }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预测" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getPredType(scope.row.prediction_result)" size="small">
              {{ scope.row.prediction_name || getResultText(scope.row.prediction_result) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="90" align="center">
          <template #default="scope">
            <span>{{ scope.row.confidence ? Math.round(scope.row.confidence) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="80" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.is_correct === 1" type="success" size="small">正确</el-tag>
            <el-tag v-else-if="scope.row.is_correct === 2" type="danger" size="small">错误</el-tag>
            <el-tag v-else type="info" size="small">待定</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="scope">
            <el-button size="small" type="primary" link @click.stop="showDetail(scope.row)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>

    <!-- 预测详情弹窗 -->
    <el-dialog v-model="dialogVisible" title="预测详情" width="700px">
      <div v-if="currentDetail" class="detail-content">
        <div class="detail-match">
          <h3>{{ currentDetail.league_name }}</h3>
          <div class="teams-line">
            <span class="home">{{ currentDetail.home_team_name }}</span>
            <span class="vs">
              <template v-if="currentDetail.actual_score">{{ currentDetail.actual_score }}</template>
              <template v-else>VS</template>
            </span>
            <span class="away">{{ currentDetail.away_team_name }}</span>
          </div>
        </div>

        <el-divider />

        <div v-if="currentDetail.prediction" class="detail-section">
          <h4>预测结果</h4>
          <div class="pred-result" :class="currentDetail.prediction.prediction">
            {{ currentDetail.prediction.prediction_name }}
            <span class="conf">(置信度 {{ Math.round(currentDetail.prediction.confidence) }}%)</span>
          </div>
          <div class="probs">
            <span>主胜 {{ Math.round(currentDetail.prediction.probabilities.home) }}%</span>
            <span>平局 {{ Math.round(currentDetail.prediction.probabilities.draw) }}%</span>
            <span>客胜 {{ Math.round(currentDetail.prediction.probabilities.away) }}%</span>
          </div>
          <div v-if="currentDetail.is_correct !== 0" class="actual">
            <el-tag v-if="currentDetail.is_correct === 1" type="success">预测正确</el-tag>
            <el-tag v-else type="danger">预测错误</el-tag>
          </div>
        </div>

        <el-divider />

        <div v-if="currentDetail.odds_analysis" class="detail-section">
          <h4>赔率分析</h4>
          <div v-if="currentDetail.odds_analysis.opening_odds">
            <el-table :data="currentDetail.odds_analysis.opening_odds" size="small">
              <el-table-column prop="bookmaker" label="博彩公司" width="100" />
              <el-table-column prop="home_odds" label="主胜" width="70" />
              <el-table-column prop="draw_odds" label="平局" width="70" />
              <el-table-column prop="away_odds" label="客胜" width="70" />
              <el-table-column prop="tendency" label="倾向" width="70">
                <template #default="scope">
                  <el-tag size="small" :type="getTendencyType(scope.row.tendency)">
                    {{ getResultText(scope.row.tendency) }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-if="currentDetail.odds_analysis.odds_change_signal" class="odds-signal">
            <el-tag type="warning">赔率变化趋势: {{ currentDetail.odds_analysis.odds_change_signal.trend || '稳定' }}</el-tag>
          </div>
        </div>

        <el-divider />

        <div v-if="currentDetail.analysis_summary && currentDetail.analysis_summary.length" class="detail-section">
          <h4>分析摘要</h4>
          <ul class="summary-list">
            <li v-for="(item, idx) in currentDetail.analysis_summary" :key="idx">{{ item }}</li>
          </ul>
        </div>

        <el-divider />

        <div v-if="currentDetail.platform_predictions && currentDetail.platform_predictions.length" class="detail-section">
          <h4>各平台预测</h4>
          <el-table :data="currentDetail.platform_predictions" size="small">
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="prediction_info.prediction_name" label="预测" width="80">
              <template #default="scope">
                {{ scope.row.prediction_info?.prediction_name || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="prediction_info.confidence" label="置信度" width="100">
              <template #default="scope">
                {{ scope.row.prediction_info?.confidence ? Math.round(scope.row.prediction_info.confidence) + '%' : '-' }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

export default {
  name: 'TeamHistory',
  setup() {
    const route = useRoute()
    const router = useRouter()
    const teamName = ref(route.params.name)
    const records = ref([])
    const loading = ref(false)
    const page = ref(1)
    const pageSize = ref(20)
    const total = ref(0)
    const stats = ref({ correct: 0, wrong: 0, pending: 0, total: 0 })
    const dialogVisible = ref(false)
    const currentDetail = ref(null)

    const accuracyRate = computed(() => {
      const total = stats.value.correct + stats.value.wrong
      return total > 0 ? Math.round(stats.value.correct / total * 100) : 0
    })

    const accuracyType = computed(() => {
      const rate = accuracyRate.value
      if (rate >= 70) return 'success'
      if (rate >= 50) return 'warning'
      return 'danger'
    })

    watch(() => route.params.name, (newName) => {
      teamName.value = newName
      page.value = 1
      loadData()
    })

    const loadData = async () => {
      loading.value = true
      try {
        const res = await api.getHistoryList({
          team: teamName.value,
          page: page.value,
          page_size: pageSize.value
        })
        records.value = res.data.records
        total.value = res.data.total

        // Calculate stats
        const correct = records.value.filter(r => r.is_correct === 1).length
        const wrong = records.value.filter(r => r.is_correct === 2).length
        const pending = records.value.filter(r => r.is_correct === 0).length
        stats.value = { correct, wrong, pending, total: records.value.length }
      } catch (e) {
        console.error('Load team history failed:', e)
      } finally {
        loading.value = false
      }
    }

    const getPredType = (result) => {
      const types = { home: 'primary', draw: 'warning', away: 'danger' }
      return types[result] || 'info'
    }

    const getResultText = (result) => {
      const map = { home: '主胜', draw: '平局', away: '客胜' }
      return map[result] || result || '-'
    }

    const getTendencyType = (tendency) => {
      const types = { home: 'primary', draw: 'warning', away: 'danger' }
      return types[tendency] || 'info'
    }

    const showDetail = async (row) => {
      try {
        const res = await api.getHistoryDetail(row.match_id)
        currentDetail.value = res.data
        dialogVisible.value = true
      } catch (e) {
        console.error('Load detail failed:', e)
      }
    }

    const goBack = () => {
      router.back()
    }

    onMounted(loadData)

    return {
      teamName,
      records,
      loading,
      page,
      pageSize,
      total,
      stats,
      accuracyRate,
      accuracyType,
      dialogVisible,
      currentDetail,
      loadData,
      getPredType,
      getResultText,
      getTendencyType,
      showDetail,
      goBack
    }
  }
}
</script>

<style scoped>
.team-history {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.team-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.team-header h1 {
  margin: 0 0 15px;
  font-size: 28px;
}

.stats-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.is-team {
  color: #409eff;
  font-weight: bold;
}

.score {
  font-weight: bold;
  font-size: 15px;
}

.pending {
  color: #c0c4cc;
}

.detail-content {
  padding: 10px;
}

.detail-match {
  text-align: center;
}

.detail-match h3 {
  color: #909399;
  font-size: 14px;
  margin-bottom: 10px;
}

.teams-line {
  font-size: 22px;
  font-weight: bold;
}

.teams-line .home {
  color: #409eff;
}

.teams-line .away {
  color: #f56c6c;
}

.teams-line .vs {
  margin: 0 20px;
  color: #909399;
}

.detail-section {
  margin-bottom: 10px;
}

.detail-section h4 {
  margin-bottom: 10px;
  color: #303133;
}

.pred-result {
  font-size: 24px;
  font-weight: bold;
  padding: 15px;
  text-align: center;
  border-radius: 8px;
  margin-bottom: 10px;
}

.pred-result.home {
  background: #ecf5ff;
  color: #409eff;
}

.pred-result.draw {
  background: #fdf6ec;
  color: #e6a23c;
}

.pred-result.away {
  background: #fef0f0;
  color: #f56c6c;
}

.pred-result .conf {
  font-size: 14px;
  font-weight: normal;
  color: #909399;
}

.probs {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin: 10px 0;
  color: #606266;
}

.actual {
  text-align: center;
  margin-top: 10px;
}

.odds-signal {
  margin-top: 10px;
}

.summary-list {
  margin: 0;
  padding-left: 20px;
}

.summary-list li {
  margin-bottom: 5px;
  color: #606266;
  line-height: 1.6;
}
</style>
