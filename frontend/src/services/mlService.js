import { api } from './api'

/**
 * Train (or retrain) the local categorization model on all confirmed transactions.
 * Returns the new model's metadata: { accuracy, n_samples, per_category, ... }
 */
export const trainCategorizer = async () => {
  const { data } = await api.post('/api/ml/train')
  return data
}

/**
 * Per-category counts + per-category accuracy from the currently loaded model.
 * Powers the Settings → Machine Learning panel.
 */
export const getTrainingDataStats = async () => {
  const { data } = await api.get('/api/ml/training-data/stats')
  return data
}

/**
 * Lightweight model summary for header badges / health checks.
 */
export const getModelInfo = async () => {
  const { data } = await api.get('/api/ml/model/info')
  return data
}
