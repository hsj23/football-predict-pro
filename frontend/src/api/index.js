import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => {
    return response
  },
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// API方法
export default {
  // 统计
  getStatistics() {
    return api.get('/statistics/overview')
  },

  // 比赛
  getMatches(params) {
    return api.get('/matches', { params })
  },

  getMatch(matchId) {
    return api.get(`/matches/${matchId}`)
  },

  getTodayMatches() {
    return api.get('/matches/today/list')
  },

  // 预测
  getMatchPredictions(matchId) {
    return api.get(`/predictions/${matchId}`)
  },

  getPredictionAnalysis(matchId) {
    return api.get(`/predictions/${matchId}/analysis`)
  },

  getPlatformAccuracy(league) {
    return api.get('/predictions/platforms/accuracy', { params: { league } })
  },

  getHotMatches(limit = 10) {
    return api.get('/statistics/hot/matches', { params: { limit } })
  },

  // 赔率
  getMatchOdds(matchId, bookmaker) {
    return api.get(`/odds/${matchId}`, { params: { bookmaker } })
  },

  getOddsAnalysis(matchId) {
    return api.get(`/odds/${matchId}/analysis`)
  },

  getKellyIndex(matchId) {
    return api.get(`/odds/${matchId}/kelly`)
  },

  compareOdds(matchId) {
    return api.get(`/odds/compare/${matchId}`)
  },

  // 统计
  getDailyAccuracy(days = 30) {
    return api.get('/statistics/accuracy/daily', { params: { days } })
  },

  getLeagueStatistics() {
    return api.get('/statistics/leagues')
  },

  // 历史记录
  getHistoryList(params) {
    return api.get('/history/list', { params })
  },

  getHistoryDetail(matchId) {
    return api.get(`/history/detail/${matchId}`)
  },

  getHistoryStatistics() {
    return api.get('/history/statistics')
  },

  getHistoryDates() {
    return api.get('/history/dates')
  },

  // 数据刷新
  refreshTodayData() {
    return api.post('/data/refresh-today')
  },

  refreshHistory() {
    return api.post('/data/refresh-history')
  },

  getDataStatus() {
    return api.get('/data/status')
  },

  // 批量预测
  batchPredict() {
    return api.post('/predict/batch')
  },

  generatePredict(request) {
    return api.post('/predict/generate', request)
  }
}
