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
