import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
    // 沙箱/Windows 下 forks pool 会因 named-pipe 受限而超时，用 threads
    pool: 'threads',
  },
})
