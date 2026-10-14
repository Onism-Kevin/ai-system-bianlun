import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import router from './router'

// S2-F1：Pinia + vue-router；S2-F2：element-plus 全量注册（骨架期即引入，
// 登录页表单/按钮/提示统一走组件库；唯一 UI 库，不引其他）。
createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
