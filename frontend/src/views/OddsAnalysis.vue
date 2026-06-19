<template>
  <div class="odds-analysis">
    <el-card v-if="match" class="match-header-card">
      <div class="match-summary">
        <span class="league-tag">
          <el-tag type="info">{{ match.league_name }}</el-tag>
        </span>
        <div class="teams">
          <span class="home">{{ match.home_team_name }}</span>
          <span class="vs">VS</span>
          <span class="away">{{ match.away_team_name }}</span>
        </div>
        <div class="time">{{ formatDate(match.match_time) }}</div>
      </div>
    </el-card>

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- 赔率对比 -->
      <el-col :span="14">
        <el-card>
          <template #header>
            <span>赔率对比</span>
          </template>
          <el-table :data="oddsData" v-loading="loading" size="small">
            <el-table-column prop="bookmaker" label="博彩公司" width="120" />
            <el-table-column prop="home_odds" label="主胜" width="80" align="center" />
            <el-table-column prop="draw_odds" label="平局" width="80" align="center" />
            <el-table-column prop="away_odds" label="客胜" width="80" align="center" />
            <el-table-column label="倾向" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.tendency" :type="getTendencyType(row.tendency)" size="small">
                  {{ getResultText(row.tendency) }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="类型" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_opening ? 'success' : 'warning'" size="small">
                  {{ row.is_opening ? '初盘' : '即时' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!oddsData.length && !loading" class="empty-state">暂无赔率数据</div>
        </el-card>
      </el-col>

      <!-- 凯利指数 -->
      <el-col :span="10">
        <el-card>
          <template #header>
            <span>凯利指数分析</span>
          </template>
          <div v-if="kellyData.length">
            <el-table :data="kellyData" size="small">
              <el-table-column prop="bookmaker" label="公司" width="100" />
              <el-table-column label="返还率" width="90" align="center">
                <template #default="{ row }">
                  <span :style="{ color: row.return_rate < 10 ? '#67c23a' : '#e6a23c' }">
                    {{ row.return_rate }}%
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="home_kelly" label="主凯利" width="80" align="center">
                <template #default="{ row }">
                  <span :style="{ color: Math.abs(row.home_kelly - 33) < 5 ? '#67c23a' : '#909399' }">
                    {{ row.home_kelly }}%
                  </span>
                </template>
              </el-table-column>
              <el-table-column prop="draw_kelly" label="平凯利" width="80" align="center" />
              <el-table-column prop="away_kelly" label="客凯利" width="80" align="center" />
            </el-table>
          </div>
          <div v-else class="empty-state">暂无凯利指数数据</div>

          <el-divider />

          <div class="kelly-explain">
            <h4>凯利指数说明</h4>
            <ul>
              <li>返还率越低，庄家抽水越少</li>
              <li>凯利指数越接近33%，比赛越均衡</li>
              <li>凯利指数 > 35% 表示市场看好该结果</li>
            </ul>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 赔率变化趋势 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <span>赔率分析总结</span>
      </template>
      <div v-if="analysis" class="analysis-summary">
        <el-row :gutter="16">
          <el-col :span="8">
            <div class="summary-item">
              <div class="summary-label">平均主胜赔率</div>
              <div class="summary-value">{{ analysis.avg_home_odds || '-' }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="summary-item">
              <div class="summary-label">平均平局赔率</div>
              <div class="summary-value">{{ analysis.avg_draw_odds || '-' }}</div>
            </div>
          </el-col>
          <el-col :span="8">
            <div class="summary-item">
              <div class="summary-label">平均客胜赔率</div>
              <div class="summary-value">{{ analysis.avg_away_odds || '-' }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
      <div v-else class="empty-state">暂无分析数据</div>
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

export default {
  name: 'OddsAnalysis',
  setup() {
    const route = useRoute()
    const matchId = route.params.id
    const match = ref(null)
    const oddsData = ref([])
    const kellyData = ref([])
    const analysis = ref(null)
    const loading = ref(false)

    async function loadMatch() {
      try {
        const res = await api.getMatch(matchId)
        match.value = res.data
      } catch (e) {
        console.error('加载比赛信息失败:', e)
      }
    }

    async function loadOdds() {
      loading.value = true
      try {
        const res = await api.getMatchOdds(matchId)
        if (res.data && res.data.odds) {
          oddsData.value = res.data.odds.map(o => ({
            ...o,
            tendency: calcTendency(o)
          }))
        }
      } catch (e) {
        console.error('加载赔率数据失败:', e)
      } finally {
        loading.value = false
      }
    }

    async function loadKelly() {
      try {
        const res = await api.getKellyIndex(matchId)
        if (res.data && res.data.kelly_index) {
          kellyData.value = res.data.kelly_index
        }
      } catch (e) {
        console.error('加载凯利指数失败:', e)
      }
    }

    async function loadAnalysis() {
      try {
        const res = await api.getOddsAnalysis(matchId)
        if (res.data) {
          analysis.value = res.data
        }
      } catch (e) {
        console.error('加载赔率分析失败:', e)
      }
    }

    function calcTendency(odds) {
      if (!odds.home_odds || !odds.draw_odds || !odds.away_odds) return null
      const h = 1 / odds.home_odds
      const d = 1 / odds.draw_odds
      const a = 1 / odds.away_odds
      const total = h + d + a
      const pHome = Math.round(h / total * 100)
      const pDraw = Math.round(d / total * 100)
      const pAway = Math.round(a / total * 100)
      const maxP = Math.max(pHome, pDraw, pAway)
      if (maxP === pHome) return 'home'
      if (maxP === pDraw) return 'draw'
      return 'away'
    }

    function getTendencyType(tendency) {
      const types = { home: '', draw: 'warning', away: 'danger' }
      return types[tendency] || 'info'
    }

    function getResultText(result) {
      const map = { home: '主胜', draw: '平局', away: '客胜' }
      return map[result] || result || '-'
    }

    function formatDate(time) {
      if (!time) return ''
      const d = new Date(time)
      return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    }

    onMounted(() => {
      loadMatch()
      loadOdds()
      loadKelly()
      loadAnalysis()
    })

    return {
      match,
      oddsData,
      kellyData,
      analysis,
      loading,
      getTendencyType,
      getResultText,
      formatDate
    }
  }
}
</script>

<style scoped>
.odds-analysis {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.match-header-card {
  text-align: center;
}

.match-summary .league-tag {
  margin-bottom: 12px;
  display: block;
}

.match-summary .teams {
  font-size: 24px;
  font-weight: bold;
  margin: 12px 0;
}

.match-summary .home { color: #409eff; }
.match-summary .away { color: #f56c6c; }
.match-summary .vs { color: #909399; margin: 0 20px; }

.match-summary .time {
  color: #909399;
  font-size: 14px;
}

.empty-state {
  text-align: center;
  color: #909399;
  padding: 40px;
}

.analysis-summary {
  padding: 10px 0;
}

.summary-item {
  text-align: center;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 22px;
  font-weight: bold;
  color: #303133;
}

.kelly-explain {
  padding: 10px 0;
}

.kelly-explain h4 {
  margin-bottom: 8px;
}

.kelly-explain ul {
  padding-left: 20px;
}

.kelly-explain li {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}
</style>
