<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  name: string
  size?: number | string
  color?: string
}>()

const iconSize = computed(() => {
  if (typeof props.size === 'number') {
    return `${props.size}px`
  }
  return props.size || '24px'
})

const iconPaths: Record<string, string> = {
  logo: `<circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M12 6v12M6 12h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="12" r="3" fill="currentColor"/>`,
  dashboard: `<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>`,
  user: `<circle cx="12" cy="7" r="4"/><path d="M5.5 21.7C3.8 20.6 2.5 18.9 2.5 17c0-2 2.5-4.7 6.25-4.7C11 12.3 13.5 15 13.5 17c0 1.9-1.3 3.6-3 4.7z"/>`,
  folder: `<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>`,
  guide: `<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><circle cx="12" cy="12" r="3"/>`,
  chat: `<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7.5 17 3 20l1.5-4.5L16.5 3.5z"/>`,
  reading: `<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>`,
  edit: `<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>`,
  'chevron-down': `<polyline points="6 9 12 15 18 9"/>`,
  'chevron-left': `<polyline points="15 18 9 12 15 6"/>`,
  'chevron-right': `<polyline points="9 18 15 12 9 6"/>`,
  sparkles: `<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>`,
  'book-open': `<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>`,
  'check-circle': `<circle cx="12" cy="12" r="10"/><polyline points="16 10 10 16 8 14"/>`,
  'message-circle': `<circle cx="12" cy="12" r="10"/><path d="M8 15s1.5-2 4-2 4 2 4 2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>`,
  email: `<rect x="3" y="4" width="18" height="16" rx="2" ry="2"/><path d="M3 8h18"/><path d="M3 16h18"/><path d="m8 5 5 5 5-5"/>`,
  lock: `<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>`,
  github: `<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1-.3-3.1-1 0 0-1.4.5-2.9 1 0 0-.9-.3-1.5-.8-.15.5-.6.9-1.2 1 0 0-1.5.7-2.4 2 0 0-.5.2-1 .1s-1.1-.3-2.3-.4c0 0-1.4.5-2.4 1 0 0-.8-.2-1.3-.6-.05.5-.25 1.1-.45 1.7 0 0-1.4.9-4 3.4v5h14.5"/>`,
  clock: `<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>`,
  flame: `<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>`,
  'trending-up': `<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>`
}

const iconContent = computed(() => {
  return iconPaths[props.name] || ''
})
</script>

<template>
  <svg
    v-if="name === 'logo'"
    :width="iconSize"
    :height="iconSize"
    :style="color ? { color } : {}"
    class="svg-icon"
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle cx="12" cy="12" r="10" fill="white"/>
    <path d="M12 6v12M6 12h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    <circle cx="12" cy="12" r="3" fill="currentColor"/>
  </svg>
  <svg
    v-else
    :width="iconSize"
    :height="iconSize"
    :style="color ? { color } : {}"
    class="svg-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    v-html="iconContent"
  />
</template>

<style scoped>
.svg-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>