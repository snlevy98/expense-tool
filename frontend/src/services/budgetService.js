import { api } from './api'

export const getBudgets = async (month, year) => {
  const { data } = await api.get('/api/budgets', { params: { month, year } })
  return data
}

export const setCap = async (subcategoryId, month, year, amount) => {
  const { data } = await api.put(
    `/api/budgets/subcategories/${subcategoryId}`,
    { amount },
    { params: { month, year } }
  )
  return data
}

export const setLock = async (subcategoryId, month, year, locked) => {
  const { data } = await api.patch(
    `/api/budgets/subcategories/${subcategoryId}/lock`,
    { locked },
    { params: { month, year } }
  )
  return data
}

export const removeBudget = async (subcategoryId, month, year) => {
  await api.delete(`/api/budgets/subcategories/${subcategoryId}`, {
    params: { month, year },
  })
}

export const getSavedBalances = async () => {
  const { data } = await api.get('/api/budgets/saved-balances')
  return data
}

export const resetSavedBalance = async (subcategoryId, value = 0) => {
  const { data } = await api.post(
    `/api/budgets/saved-balances/${subcategoryId}/reset`,
    { value }
  )
  return data
}

export const setTransactionExclusion = async (transactionId, budgetExcluded) => {
  const { data } = await api.patch(
    `/api/transactions/${transactionId}/budget-exclusion`,
    { budget_excluded: budgetExcluded }
  )
  return data
}

export const getExclusionRules = async () => {
  const { data } = await api.get('/api/budgets/exclusion-rules')
  return data
}

export const createExclusionRule = async (rule) => {
  const { data } = await api.post('/api/budgets/exclusion-rules', rule)
  return data
}

export const deleteExclusionRule = async (ruleId) => {
  await api.delete(`/api/budgets/exclusion-rules/${ruleId}`)
}

export const suggestBudget = async (month, year, monthsBack = 6) => {
  const { data } = await api.post('/api/budgets/suggest', null, {
    params: { month, year, months_back: monthsBack },
  })
  return data
}

export const applySuggestions = async (month, year, items) => {
  const { data } = await api.post('/api/budgets/apply-suggestions', { month, year, items })
  return data
}
