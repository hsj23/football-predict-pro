<template>
  <div class="match-list">
    <el-card>
      <template #header>
        <div class="header">
          <span>比赛列表</span>
          <div class="filters">
            <el-date-picker
              v-model="selectedDate"
              type="date"
              placeholder="选择日期"
              @change="loadMatches"
            />
            <el-select v-model="selectedLeague" placeholder="选择联赛" clearable @change="loadMatches">
              <el-option v-for="league in leagues" :key="league" :label="league" :value="league" />
            </el-select>
          </div>
        </div>
      </template>

      <el-table :data="matches" v-loading="loading" style="width: 100%">
        <el-table-column prop="league_name" label="联赛" width="120">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.league_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="match_time" label="时间" width="150">
          <template #default="scope">
            {{ formatDateTime(scope.row.match_time) }}
          </template>
        </el-table-column>
        <el-table-column label="主队">
          <template #default="scope">
            <router-link :to="'/team/' + encodeURIComponent(scope.row.home_team_name)" class="team-link home">
              {{ scope.row.home_team_name }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="比分" width="100" align="center">
          <template #default="scope">
            <div v-if="scope.row.status === 'finished'" class="score">
              {{ scope.row.home_score }} - {{ scope.row.away_score }}
            </div>
            <div v-else class="vs">VS</div>
          </template>
        </el-table-column>
        <el-table-column label="客队">
          <template #default="scope">
            <router-link :to="'/team/' + encodeURIComponent(scope.row.away_team_name)" class="team-link away">
              {{ scope.row.away_team_name }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)">
              {{ getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button-group>
              <el-button size="small" type="primary" @click="viewPrediction(scope.row)">
                预测分析
              </el-button>
              <el-button size="small" @click="viewOdds(scope.row)">
                赔率
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadMatches"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

export default {
  name: 'MatchList',
  setup() {
    const router = useRouter()
    const matches = ref([])
    const loading = ref(false)
    const selectedDate = ref(new Date())
    const selectedLeague = ref('')
    const currentPage = ref(1)
    const pageSize = ref(20)
    const total = ref(0)

    const leagues = computed(() => {
      const leagueSet = new Set()
      matches.value.forEach(m => {
        if (m.league_name) leagueSet.add(m.league_name)
      })
      return Array.from(leagueSet)
    })

    const loadMatches = async () => {
      loading.value = true
      try {
        const params = {
          limit: pageSize.value,
          offset: (currentPage.value - 1) * pageSize.value
        }
        if (selectedDate.value) {
          params.date = selectedDate.value.toISOString().split('T')[0]
        }
        if (selectedLeague.value) {
          params.league = selectedLeague.value
        }

        const response = await api.getMatches(params)
        matches.value = response.data.items
        total.value = response.data.total
      } catch (error) {
        console.error('加载比赛失败:', error)
      } finally {
        loading.value = false
      }
    }

    const formatDateTime = (time) => {
      if (!time) return ''
      const date = new Date(time)
      return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
    }

    const getStatusType = (status) => {
      const types = {
        scheduled: 'info',
        in_progress: 'warning',
        finished: 'success'
      }
      return types[status] || 'info'
    }

    const getStatusText = (status) => {
      const texts = {
        scheduled: '未开始',
        in_progress: '进行中',
        finished: '已结束'
      }
      return texts[status] || status
    }

    const viewPrediction = (match) => {
      router.push(`/prediction/${match.match_id}`)
    }

    const viewOdds = (match) => {
      router.push(`/odds/${match.match_id}`)
    }

    onMounted(() => {
      loadMatches()
    })

    return {
      matches,
      loading,
      selectedDate,
      selectedLeague,
      leagues,
      currentPage,
      pageSize,
      total,
      loadMatches,
      formatDateTime,
      getStatusType,
      getStatusText,
      viewPrediction,
      viewOdds
    }
  }
}
</script>

<style scoped>
.match-list {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filters {
  display: flex;
  gap: 10px;
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

.score {
  font-weight: bold;
  font-size: 16px;
}

.vs {
  color: #909399;
}
</style>
