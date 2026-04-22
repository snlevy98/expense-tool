import { api } from './api'

export const getAccounts = async () => {
  const { data } = await api.get('/api/accounts')
  return data
}

export const createAccount = async (accountData) => {
  const { data } = await api.post('/api/accounts', accountData)
  return data
}

export const updateAccount = async (id, accountData) => {
  const { data } = await api.put(`/api/accounts/${id}`, accountData)
  return data
}

export const deleteAccount = async (id) => {
  const { data } = await api.delete(`/api/accounts/${id}`)
  return data
}
