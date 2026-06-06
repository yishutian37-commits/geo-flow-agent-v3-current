import axios from 'axios';

const runtimeApiBaseUrl = window.geoDesktop?.apiBaseUrl || window.__GEO_API_BASE__ || '';
const API_BASE_URL = runtimeApiBaseUrl || process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

const AI_GENERATION_TIMEOUT = 300000;

export const apiAssetUrl = (path) => {
  if (!path) return '';
  if (/^(https?:|data:|file:)/i.test(path)) return path;
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}${path.startsWith('/') ? '' : '/'}${path}`;
};

const toQueryString = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== '') {
          search.append(key, item);
        }
      });
      return;
    }
    search.append(key, value);
  });
  const query = search.toString();
  return query ? `?${query}` : '';
};

// Request interceptor for auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Projects API
export const authApi = {
  bootstrapStatus: () => api.get('/auth/bootstrap/status'),
  bootstrapAdmin: (data) => api.post('/auth/bootstrap-admin', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
};

// Users API
export const usersApi = {
  listRoles: () => api.get('/users/roles'),
  list: (params) => api.get('/users', { params }),
  create: (data) => api.post('/users', data),
  update: (id, data) => api.put(`/users/${id}`, data),
  resetPassword: (id, data) => api.post(`/users/${id}/reset-password`, data),
  deactivate: (id) => api.delete(`/users/${id}`),
};

// Projects API
export const projectsApi = {
  list: (params) => api.get('/projects', { params }),
  get: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.put(`/projects/${id}`, data),
  delete: (id) => api.delete(`/projects/${id}`),
  diagnoseGaps: (id, providedFields) => api.post(`/projects/${id}/diagnose-gaps`, providedFields),
  diagnoseGapsFromFacts: (id) => api.get(`/projects/${id}/diagnose-gaps-from-facts`),
  getDiagnosisReport: (id) => api.get(`/projects/${id}/diagnosis-report`),
  getBrandFactsSummary: (id) => api.get(`/projects/${id}/brand-facts-summary`),
  getBrands: (id) => api.get(`/projects/${id}/brands`),
  generateQuestionBank: (id, brandName) => api.post(`/projects/${id}/generate-question-bank`, null, { params: { brand_name: brandName }, timeout: AI_GENERATION_TIMEOUT }),
  generateContentMatrix: (id, data = {}) => api.post(`/projects/${id}/generate-content-matrix`, data, { timeout: AI_GENERATION_TIMEOUT }),
};

// Brands API
export const brandsApi = {
  list: (params) => api.get('/brands', { params }),
  get: (id) => api.get(`/brands/${id}`),
  create: (data) => api.post('/brands', data),
};

// Brand Facts API
export const brandFactsApi = {
  list: (params) => api.get('/brand-facts', { params }),
  get: (id) => api.get(`/brand-facts/${id}`),
  create: (data) => api.post('/brand-facts', data),
  update: (id, data) => api.put(`/brand-facts/${id}`, data),
  confirm: (id, publicWording) => api.post(`/brand-facts/${id}/confirm`, { public_wording: publicWording }),
  confirmWithEvidence: (id, data) => api.post(`/brand-facts/${id}/confirm`, data),
  history: (id, params) => api.get(`/brand-facts/${id}/history`, { params }),
  checkForPublish: (factIds) => api.post('/brand-facts/check-for-publish', factIds),
  extractFromCorpus: (corpusItemId, suggestedFacts) => api.post('/brand-facts/extract-from-corpus', { corpus_item_id: corpusItemId, suggested_facts: suggestedFacts }, { timeout: AI_GENERATION_TIMEOUT }),
  extractFromText: (data) => api.post('/brand-facts/extract-from-text', data, { timeout: AI_GENERATION_TIMEOUT }),
};

// AI Models API
export const aiModelsApi = {
  listProviders: () => api.get('/ai-models/providers'),
  listChoices: () => api.get('/ai-models/providers/choices'),
  listRegistry: () => api.get('/ai-models/registry'),
  addModel: (data) => api.post('/ai-models/registry/add', null, { params: data }),
  setDefault: (id) => api.post(`/ai-models/registry/${id}/set-default`),
  updateKey: (id, apiKey) => api.post(`/ai-models/registry/${id}/update-key`, { api_key: apiKey }),
  updateModel: (id, data) => api.post(`/ai-models/registry/${id}/update`, data),
  removeModel: (id) => api.delete(`/ai-models/registry/${id}`),
  test: (data) => api.post('/ai-models/test', data),
  getCostSummary: () => api.get('/ai-models/cost/summary'),
};

// Platform Policies API
export const platformPoliciesApi = {
  list: () => api.get('/platform-policies'),
  get: (platform) => api.get(`/platform-policies/${platform}`),
  update: (platform, data) => api.put(`/platform-policies/${platform}`, data),
  check: (data) => api.post('/platform-policies/check', data),
};

// Question Archetypes API
export const questionArchetypesApi = {
  list: () => api.get('/question-archetypes'),
  get: (industry) => api.get(`/question-archetypes/${industry}`),
  update: (industry, data) => api.put(`/question-archetypes/${industry}`, data),
  suggestions: (params) => api.get('/question-archetypes/learning/suggestions', { params }),
  feedbacks: (params) => api.get('/question-archetypes/learning/feedbacks', { params }),
  applySuggestion: (data) => api.post('/question-archetypes/learning/apply', data),
};

// Corpus Items API
export const corpusItemsApi = {
  list: (params) => api.get('/corpus-items', { params }),
  create: (data) => api.post('/corpus-items', null, { params: data }),
  get: (id) => api.get(`/corpus-items/${id}`),
  update: (id, data) => api.put(`/corpus-items/${id}`, null, { params: data }),
  delete: (id) => api.delete(`/corpus-items/${id}`),
};

// Source Assets API
export const sourceAssetsApi = {
  list: (params) => api.get('/source-assets', { params }),
  create: (data) => api.post('/source-assets', data),
  get: (id) => api.get(`/source-assets/${id}`),
  update: (id, data) => api.put(`/source-assets/${id}`, data),
  delete: (id) => api.delete(`/source-assets/${id}`),
};

// Content Tasks API
export const contentTasksApi = {
  list: (params) => api.get('/content-tasks', { params }),
  create: (data) => api.post('/content-tasks', data),
  get: (id) => api.get(`/content-tasks/${id}`),
  update: (id, data) => api.put(`/content-tasks/${id}`, data),
  transition: (id, data) => api.post(`/content-tasks/${id}/transition`, data),
  delete: (id) => api.delete(`/content-tasks/${id}`),
};

// Content Drafts API
export const contentDraftsApi = {
  list: (params) => api.get('/content-drafts', { params }),
  create: (data) => api.post('/content-drafts', data),
  get: (id) => api.get(`/content-drafts/${id}`),
  update: (id, data) => api.put(`/content-drafts/${id}`, data),
  delete: (id) => api.delete(`/content-drafts/${id}`),
  generate: (taskId, data) => api.post(`/content-drafts/${taskId}/generate`, data, { timeout: AI_GENERATION_TIMEOUT }),
  validatePublishReady: (id) => api.post(`/content-drafts/${id}/validate-publish-ready`),
};

// Channel Accounts API
export const channelAccountsApi = {
  list: (params) => api.get('/channel-accounts', { params }),
  create: (data) => api.post('/channel-accounts', data),
  get: (id) => api.get(`/channel-accounts/${id}`),
  update: (id, data) => api.put(`/channel-accounts/${id}`, data),
  delete: (id) => api.delete(`/channel-accounts/${id}`),
};

// Model Targets API
export const modelTargetsApi = {
  list: (params) => api.get('/model-targets', { params }),
  create: (data) => api.post('/model-targets', data),
  get: (id) => api.get(`/model-targets/${id}`),
  update: (id, data) => api.put(`/model-targets/${id}`, data),
  delete: (id) => api.delete(`/model-targets/${id}`),
};

// Baseline Runs API
export const baselineRunsApi = {
  list: (params) => api.get('/baseline-runs', { params }),
  create: (data) => api.post('/baseline-runs', data),
  update: (id, data) => api.put(`/baseline-runs/${id}`, data),
  invalidate: (id, reason) => api.post(`/baseline-runs/${id}/invalidate`, null, { params: { reason } }),
  promoteFromRun: (runId, data = {}) => api.post(`/baseline-runs/from-monitoring-run/${runId}`, data),
};

// Publish Records API
export const publishRecordsApi = {
  list: (params) => api.get('/publish-records', { params }),
  create: (data) => api.post('/publish-records', data),
  webbridgeAssist: (data) => api.post('/publish-records/webbridge-assist', data),
  get: (id) => api.get(`/publish-records/${id}`),
  update: (id, data) => api.put(`/publish-records/${id}`, data),
  delete: (id) => api.delete(`/publish-records/${id}`),
};

// Writing Memory API
export const writingMemoryApi = {
  listFeedbacks: (params) => api.get('/writing-memory/feedbacks', { params }),
  countUnfolded: (projectId) => api.get('/writing-memory/feedbacks/count', { params: { project_id: projectId } }),
  createFeedback: (data) => api.post('/writing-memory/feedbacks', data, { timeout: AI_GENERATION_TIMEOUT }),
  updateFeedback: (id, data) => api.put(`/writing-memory/feedbacks/${id}`, data),
  deleteFeedback: (id) => api.delete(`/writing-memory/feedbacks/${id}`),
  getProfile: (projectId) => api.get(`/writing-memory/profiles/${projectId}`),
  updateProfile: (projectId, data) => api.put(`/writing-memory/profiles/${projectId}`, data),
  foldProfile: (projectId, data = {}) => api.post(`/writing-memory/profiles/${projectId}/fold`, data, { timeout: AI_GENERATION_TIMEOUT }),
};

// Questions API
export const questionsApi = {
  listGroups: (params) => api.get('/questions/groups', { params }),
  createGroup: (data) => api.post('/questions/groups', data),
  getGroup: (id) => api.get(`/questions/groups/${id}`),
  updateGroup: (id, data) => api.put(`/questions/groups/${id}`, data),
  createQuestion: (groupId, data) => api.post(`/questions/groups/${groupId}/questions`, data),
  updateQuestion: (id, data) => api.put(`/questions/${id}`, data),
  deleteQuestion: (id) => api.delete(`/questions/${id}`),
  listQuestions: (params) => api.get('/questions', { params }),
};

// Monitoring API
export const monitoringApi = {
  webbridgeStatus: () => api.get('/monitoring/webbridge/status'),
  listRuns: (params) => api.get('/monitoring/runs', { params }),
  listSamples: (params) => api.get('/monitoring/samples', { params }),
  sourceAnalysis: (params) => api.get('/monitoring/source-analysis', { params }),
  createRun: (data) => api.post('/monitoring/runs', null, { params: data }),
  getRun: (id) => api.get(`/monitoring/runs/${id}`),
  deleteRun: (id) => api.delete(`/monitoring/runs/${id}`),
  updateRunStatus: (id, status) => api.post(`/monitoring/runs/${id}/status`, { status }),
  addSample: (runId, data) => api.post(`/monitoring/runs/${runId}/samples`, null, { params: data }),
  deleteSample: (id) => api.delete(`/monitoring/samples/${id}`),
  createContentTaskFromSample: (id, data = {}) => api.post(`/monitoring/samples/${id}/content-task`, data),
  webbridgeSample: (runId, data, config = {}) => api.post(
    `/monitoring/runs/${runId}/webbridge-sample`,
    data,
    { timeout: Math.max(((data?.wait_seconds || 60) + 120) * 1000, 180000), ...config }
  ),
  calculateMetrics: (id) => api.post(`/monitoring/runs/${id}/calculate`),
  compareWithBaseline: (runId, baselineRunId) => api.post(`/monitoring/runs/${runId}/compare/${baselineRunId}`),
  generateRecommendations: (id) => api.post(`/monitoring/runs/${id}/recommendations`),
};

// Sentiments API
export const sentimentsApi = {
  list: (params) => api.get('/sentiments', { params }),
  create: (data) => api.post('/sentiments', data),
  update: (id, data) => api.put(`/sentiments/${id}`, data),
  delete: (id) => api.delete(`/sentiments/${id}`),
};

// Approvals API
export const approvalsApi = {
  list: (params) => api.get('/approvals', { params }),
  create: (data) => api.post('/approvals', data),
  decide: (id, data) => api.post(`/approvals/${id}/decision`, data),
};

// Reports API
export const reportsApi = {
  generate: (params) => api.get(`/reports${toQueryString(params)}`),
  markdown: (params) => api.get(`/reports/markdown${toQueryString(params)}`, { responseType: 'text' }),
  archiveGenerate: (data) => api.post('/reports/archives', data),
  archives: (params) => api.get('/reports/archives', { params }),
  archiveDetail: (id) => api.get(`/reports/archives/${id}`),
  archiveMarkdown: (id) => api.get(`/reports/archives/${id}/markdown`, { responseType: 'text' }),
  deleteArchive: (id) => api.delete(`/reports/archives/${id}`),
};

// Dashboard API
export const dashboardApi = {
  getStats: () => api.get('/dashboard/stats'),
};

export default api;
