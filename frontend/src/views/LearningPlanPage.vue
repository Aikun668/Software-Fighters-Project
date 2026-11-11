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
const actionPlanTitle = computed(() => actionSnapshot.value?.active_plan?.title || '本周学习计划')
const actionTopic = computed(() => currentStep.value?.topic || actionSnapshot.value?.current_node?.name || '当前学习内容')
const canCompleteAction = computed(() => Boolean(actionPlanId.value && actionStepId.value))
// 实际用时与自评由用户填写：不再固定提交 score: 1（满分）/ duration_minutes: 0 的虚假数据。
const actionMinutes = ref<number | null>(null)
const actionLevel = ref('')
const levelScore: Record<string, number> = { solid: 0.9, shaky: 0.6, stuck: 0.3 }
const canSubmitAction = computed(() => canCompleteAction.value
  && typeof actionMinutes.value === 'number' && Number.isFinite(actionMinutes.value)
  && actionMinutes.value > 0 && actionMinutes.value <= 600
  && Boolean(levelScore[actionLevel.value]))

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
  if (!canSubmitAction.value) {
    actionError.value = '请先填写本次实际用时（1–600 分钟）并选择自评结果，再提交。'
    return
  }
  // 到这里的取值都由 canSubmitAction 保证过，取出来给 TS 一个确定类型
  const minutes = actionMinutes.value
  const score = levelScore[actionLevel.value]
  if (minutes === null || score === undefined) {
    actionError.value = '请先填写本次实际用时（1–600 分钟）并选择自评结果，再提交。'
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
      score,
      duration_minutes: minutes,
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
        <small>本动作记录到学习快照里的「{{ actionPlanTitle }}」<template v-if="actionPlanId">（计划 #{{ actionPlanId }}）</template>，不会自动改动下面的自适应计划。</small>
        <small v-if="route.query.source === 'learning_snapshot'">本次动作来自学习快照建议，完成后会重新读取学情。</small>
      </div>
      <div class="action-context-controls">
        <span v-if="actionLoading" class="action-status">正在读取计划步骤…</span>
        <span v-else-if="actionError" class="action-error">{{ actionError }}</span>
        <template v-else>
          <label class="action-field">实际用时
            <input v-model.number="actionMinutes" data-test="action-minutes" type="number" min="1" max="600" placeholder="分钟" />
            <span>分钟</span>
          </label>
          <label class="action-field">自评
            <select v-model="actionLevel" data-test="action-level">
              <option value="">请选择</option>
              <option value="solid">已能独立完成</option>
              <option value="shaky">基本会，还需练习</option>
              <option value="stuck">还不熟，需要再看</option>
            </select>
          </label>
          <button
            data-test="complete-learning-action"
            class="primary-action"
            :disabled="actionSubmitting || !canSubmitAction"
            @click="completeLearningAction"
          >
            {{ actionSubmitting ? '正在提交…' : '完成本次动作' }}
            <Check :size="15" />
          </button>
        </template>
      </div>
      <small class="action-note">用时和自评来自你本人的填写，不是测验成绩。</small>
    </section>

    <AdaptivePlanWorkspace :plan-id="typeof route.query.planId === 'string' ? route.query.planId : undefined" />
  </div>
</template>
<style scoped>
.plan-page{height:100%;overflow:auto;background:#f7faf7}.learning-action-context{margin:32px;padding:24px;background:white;border:1px solid #dbe6df;border-radius:16px}.action-context-controls{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}.action-field{display:flex;flex-direction:column;gap:4px;font-size:13px;color:#41564c}.action-field input,.action-field select{padding:8px;border:1px solid #cfdcd4;border-radius:8px}.action-note{display:block;margin-top:10px;color:#6b7d74}.primary-action{padding:10px 18px;background:#285e4c;color:white;border:0;border-radius:8px}.primary-action:disabled{opacity:.55;cursor:not-allowed}.action-error{color:#a54530}
</style>
