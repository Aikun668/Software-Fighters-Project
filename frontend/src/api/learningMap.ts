import api from '@/utils/request'
export interface LearningSource { conversationId: number | string; messageId: number | string; quote: string; createdAt?: string }
export interface LearningNode { id: string; title: string; summary?: string; sources: LearningSource[]; firstSeen?: string; lastSeen?: string }
export interface LearningEdge { id: string; source: string; target: string; relation: string; evidence: LearningSource }
export interface LearningEvent { id: string; type: 'goal' | 'question' | 'practice_request' | 'practice_self_report'; title: string; nodeIds: string[]; sources: LearningSource[]; occurredAt?: string }
export interface LearningSuggestion { id: string; source: string; target: string; reason: string; status: 'pending' | 'accepted' | 'rejected'; sources: LearningSource[] }
export interface LearningMap { events?: LearningEvent[]; suggestions?: LearningSuggestion[]; nodes: LearningNode[]; edges: LearningEdge[]; meta?: { unavailable?: boolean; truncated?: boolean; extraction?: string } }
export const getLearningMap = () => api.get<LearningMap>('/learning-map')

export const decideSuggestion = (id: string, decision: 'accepted' | 'rejected') => api.post(`/learning-map/suggestions/${encodeURIComponent(id)}/decision`, { decision })
export const getContinuation = (id: string) => api.get<{ draft: string }>(`/learning-map/nodes/${encodeURIComponent(id)}/continuation`)
