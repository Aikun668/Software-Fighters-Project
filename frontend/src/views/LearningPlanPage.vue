<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check } from '@lucide/vue'
import AdaptivePlanWorkspace from '@/components/plans/AdaptivePlanWorkspace.vue'
import { getLearningSnapshot, type LearningSnapshot } from '@/api/learningSnapshot'
import { updatePlanProgress } from '@/api/plans'
import { resolveErrorMessage } from '@/utils/request'
const router = useRouter(), route = useRoute()
const actionSnapshot = ref<LearningSnapshot | null>(null)
const actionLoading = ref(false), actionSubmitting = ref(false), actionError = ref('')
const queryValue = (value: unknown) => typeof value === 'string' ? value : ''
const courseId = computed(() => queryValue(route.query.courseId) || 'ai_intro')
const actionKind = computed(() => queryValue(route.query.actionKind))
const isPlanAction = computed(() => actionKind.value === 'resume_plan' || actionKind.value === 'review_current_node')
const actionTitle = computed(() => actionKind.value === 'review_current_node' ? '复习当前知识点' : '继续本周计划')
const actionActivityType = computed(() => actionKind.value === 'review_current_node' ? 'review' : 'study')
const currentStep = computed(() => actionSnapshot.value?.active_plan?.current_step ?? null)
const actionStepId = computed(() => {
  const fromQuery = Number(queryValue(route.query.stepId))
  return Number.isInteger(fromQuery) && fromQuery > 0 ? fromQuery : currentStep.value?.step_id ?? null
})
const actionPlanId = computed(() => actionSnapshot.value?.active_plan?.plan_id ?? null)
const actionTopic = computed(() => currentStep.value?.topic || actionSnapshot.value?.current_node?.name || '当前学习内容')
const canCompleteAction = computed(() => Boolean(actionPlanId.value && actionStepId.value))

const loadActionSnapshot = async () => {
  if (!isPlanAction.value) return
  actionLoading.value = true
  actionError.value = ''
  try {
    actionSnapshot.value = await getLearningSnapshot(courseId.value)
  } catch (error) {
    actionError.value = resolveErrorMessage(error)
  } finally {
    actionLoading.value = false
  }
}

const completeLearningAction = async () => {
  if (!canCompleteAction.value || !actionPlanId.value || !actionStepId.value) {
    actionError.value = '当前快照没有可提交的计划步骤，请返回学习入口重新读取。'
    return
  }

  actionSubmitting.value = true
  actionError.value = ''
  try {
    const response = await updatePlanProgress(actionPlanId.value, {
      step_id: actionStepId.value,
      step_order: currentStep.value?.order ?? 0,
      status: 'completed',
      activity_type: actionActivityType.value,
      score: 1,
      duration_minutes: 0,
    })
    const status = response.message || response.status || '计划动作已提交'
    await router.push({ path: '/learning-analysis', query: { courseId: courseId.value, progressStatus: status } })
  } catch (error) {
    actionError.value = resolveErrorMessage(error)
  } finally {
    actionSubmitting.value = false
  }
}

onMounted(() => { void loadActionSnapshot() })
</script>
<template>
  <div class="plan-page">
    <section v-if="isPlanAction" class="learning-action-context" aria-live="polite">
      <div class="action-context-copy">
        <span class="eyebrow">从学习入口进入</span>
        <h2>{{ actionTitle }}</h2>
        <p>当前目标：{{ actionTopic }}</p>
        <small v-if="route.query.source === 'learning_snapshot'">本次动作来自学习快照建议，完成后会重新读取学情。</small>
      </div>
      <div class="action-context-controls">
        <span v-if="actionLoading" class="action-status">正在读取计划步骤…</span>
        <span v-else-if="actionError" class="action-error">{{ actionError }}</span>
        <button
          v-else
          data-test="complete-learning-action"
          class="primary-action"
          :disabled="actionSubmitting || !canCompleteAction"
          @click="completeLearningAction"
        >
          {{ actionSubmitting ? '正在提交…' : '完成本次动作' }}
          <Check :size="15" />
        </button>
      </div>
    </section>

    <AdaptivePlanWorkspace v-if="!isPlanAction" :plan-id="typeof route.query.planId === 'string' ? route.query.planId : undefined" />
  </div>
</template>
<style scoped>
.plan-page{height:100%;overflow:auto;background:#f7faf7}.learning-action-context{margin:32px;padding:24px;background:white;border:1px solid #dbe6df;border-radius:16px}.action-context-controls{display:flex;gap:12px}.primary-action{padding:10px 18px;background:#285e4c;color:white;border:0;border-radius:8px}.action-error{color:#a54530}
</style>
