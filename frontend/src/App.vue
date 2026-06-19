<template>
  <div id="app">
    <el-container>
      <el-header>
        <div class="logo">FootballPredict Pro</div>
        <el-menu
          :default-active="activeIndex"
          mode="horizontal"
          @select="handleSelect"
          router
        >
          <el-menu-item index="/">首页</el-menu-item>
          <el-menu-item index="/matches">比赛列表</el-menu-item>
          <el-menu-item index="/statistics">AI预测</el-menu-item>
        </el-menu>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
      <el-footer>
        FootballPredict Pro &copy; 2026 - 仅供研究参考
      </el-footer>
    </el-container>
  </div>
</template>

<script>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

export default {
  name: 'App',
  setup() {
    const route = useRoute()
    const activeIndex = computed(() => route.path)

    const handleSelect = (index) => {
      console.log('Selected:', index)
    }

    return {
      activeIndex,
      handleSelect
    }
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
}

.el-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.logo {
  color: white;
  font-size: 20px;
  font-weight: bold;
  margin-right: 40px;
}

.el-header .el-menu {
  background: transparent;
  border-bottom: none;
}

.el-header .el-menu-item {
  color: rgba(255, 255, 255, 0.8);
  border-bottom: none;
}

.el-header .el-menu-item:hover,
.el-header .el-menu-item.is-active {
  color: white;
  background: rgba(255, 255, 255, 0.1);
}

.el-main {
  min-height: calc(100vh - 120px);
  background: #f5f7fa;
}

.el-footer {
  text-align: center;
  color: #909399;
  font-size: 12px;
  line-height: 60px;
  background: #fff;
  border-top: 1px solid #eee;
}
</style>
