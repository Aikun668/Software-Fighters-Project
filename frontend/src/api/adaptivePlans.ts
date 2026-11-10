import api from '@/utils/request'
export type AdaptiveTaskStatus = 'pending' | 'in_progress' | 'paused' | 'blocked' | 'completed' | 'deferred'
export interface AdaptiveTask { id: string; title: string; minutes: number; status: AdaptiveTaskStatus; checkpoint: string; nextAction: string }
export interface AdaptiveModule { id: string; title: string; tasks: AdaptiveTask[] }
export interface AdaptivePlan { id: string; title: string; goal: string; dailyMinutes: number; deadline: string | null; version: number; status: string; modules: AdaptiveModule[]; history: Array<{message?: string; action?: string; createdAt?: string; [key: string]: unknown}>; canUndo?: boolean; capacityWarning?: string | null }
export interface PlanProposal { proposedPlan?: AdaptivePlan; extendedDeadline?: string; deferredTasks?: AdaptiveTask[]; id: string; baseVersion: number; message?: string; changes: Array<{kind: string; taskId?: string; before: unknown; after: unknown}>; conflict: string | null | {message?: string; [key: string]: unknown}; [key: string]: unknown }
export interface CreateAdaptivePlan { title: string; goal: string; dailyMinutes: number; deadline: string | null; modules: Array<{title: string; tasks: Array<{ title: string; minutes: number }>}> }
const path = (id: string) => `/adaptive-plans/${encodeURIComponent(id)}`
export const listAdaptivePlans = () => api.get<AdaptivePlan[]>('/adaptive-plans')
export const getAdaptivePlan = (id: string) => api.get<AdaptivePlan>(path(id))
export const createAdaptivePlan = (body: CreateAdaptivePlan) => api.post<AdaptivePlan>('/adaptive-plans', body)
export const updateAdaptiveTask = (id: string, taskId: string, body: {version: number; status: AdaptiveTaskStatus; checkpoint: string; nextAction: string}) => api.patch<AdaptivePlan>(`${path(id)}/tasks/${encodeURIComponent(taskId)}`, body)
export const proposeAdjustment = (id: string, body: {version: number; message: string; dailyMinutes?: number; deadline?: string; taskId?: string}) => api.post<PlanProposal>(`${path(id)}/proposals`, body)
export const applyAdjustment = (id: string, proposalId: string, body: {version: number; resolution?: string}) => api.post<AdaptivePlan>(`${path(id)}/proposals/${encodeURIComponent(proposalId)}/apply`, body)
export const undoAdjustment = (id: string, body: {version: number}) => api.post<AdaptivePlan>(`${path(id)}/undo`, body)

export const addAdaptiveTask = (id: string, moduleId: string, body: {version: number; title: string; minutes: number; nextAction?: string}) => api.post<AdaptivePlan>(`${path(id)}/modules/${encodeURIComponent(moduleId)}/tasks`, body)
