import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// KaTeX 公式样式：对话正文里的数学公式排版依赖它（缺了会退化成错位的裸字符）
import 'katex/dist/katex.min.css'
import './styles/variables.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
// @ts-ignore
import uCharts from '@qiun/ucharts'

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate)
const app = createApp(App)

app.use(router)
app.use(pinia)
app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.config.globalProperties.$uCharts = uCharts

app.mount('#app')
