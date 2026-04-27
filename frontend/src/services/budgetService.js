import { api } from './api'

export const getBudgets = async (month, year) => {
  const { data } = await api.get('/api/budgets', { params: { month, year } })
  return data
}

export const upsertBudget = async (budgetData) => {
  const { data } = await api.post('/api/budgets', budgetData)
  return data
}

export const updateBudgetDefault = async (categoryId, defaultAmount) => {
  const { data } = await api.put(`/api/budgets/defaults/${categoryId}`, {
    default_amount: defaultAmount,
  })
  return data
}

export const getBudgetSettings = async () => {
  const { data } = await api.get('/api/budgets/settings')
  return data
}

export const updateBudgetSettings = async (poolPct) => {
  const { data } = await api.put('/api/budgets/settings', { pool_pct: poolPct })
  return data
}

export const fillFromLastMonth = async (month, year) => {
  const { data } = await api.post('/api/budgets/fill-from-last-month', null, {
    params: { month, year },
  })
  return data
}
