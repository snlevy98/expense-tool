import { api } from './api'

export const getTransactions = async (params = {}) => {
  const { data } = await api.get('/api/transactions', { params })
  return data
}

export const updateTransaction = async (id, transactionData) => {
  const { data } = await api.put(`/api/transactions/${id}`, transactionData)
  return data
}

export const deleteTransaction = async (id) => {
  const { data } = await api.delete(`/api/transactions/${id}`)
  return data
}

export const exportTransactions = async (params = {}) => {
  const response = await api.get('/api/transactions/export', {
    params,
    responseType: 'blob',
  })
  const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `transactions-export-${new Date().toISOString().split('T')[0]}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
