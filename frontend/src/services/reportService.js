import { api } from './api'

export const getDashboard = async (month, year) => {
  const { data } = await api.get('/api/reports/dashboard', { params: { month, year } })
  return data
}

export const getTrends = async (months = 12, categoryId = null) => {
  const params = { months }
  if (categoryId) params.category_id = categoryId
  const { data } = await api.get('/api/reports/trends', { params })
  return data.points ?? []
}

export const getTopMerchants = async (month, year, limit = 10) => {
  const { data } = await api.get('/api/reports/top-merchants', {
    params: { month, year, limit },
  })
  return data
}

export const getYTD = async (year) => {
  const { data } = await api.get('/api/reports/ytd', { params: { year } })
  return data.categories ?? []
}

export const getRecurring = async () => {
  const { data } = await api.get('/api/reports/recurring')
  return data
}
