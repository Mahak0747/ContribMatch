import type {
  AnalyticsResponse, HealthResponse, HistoryResponse, ProfileInput, RecommendationRun, SavedProfile,
} from '../types/api'
import { http, toApiError } from './client'

async function call<T>(fn: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await fn()).data
  } catch (e) {
    throw toApiError(e)
  }
}

export const getHealth = () => call<HealthResponse>(() => http.get('/health', { timeout: 5_000 }))

export const saveProfile = (profile: ProfileInput) => call<SavedProfile>(() => http.post('/profile', profile))

/** Slow on the very first call: GitHub search plus a one-time local model download/load. */
export const createRecommendations = (profileId: number, topK = 10) =>
  call<RecommendationRun>(() => http.post('/recommendations', { profile_id: profileId, top_k: topK }, { timeout: 180_000 }))

export const getRecommendation = (id: number) => call<RecommendationRun>(() => http.get(`/recommendations/${id}`))

export const getHistory = (limit = 10, offset = 0) =>
  call<HistoryResponse>(() => http.get('/history', { params: { limit, offset } }))

export const getAnalytics = () => call<AnalyticsResponse>(() => http.get('/analytics'))
