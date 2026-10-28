<template>
  <div id="app">
    <router-view />
  </div>
</template>

<style>
/* 全局重置与基础样式 */
html,
body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  background-color: #f1f5f9;
  -webkit-font-smoothing: antialiased;
}

#app {
  width: 100%;
  height: 100vh;
}

/* 滚动条美化 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
</style>