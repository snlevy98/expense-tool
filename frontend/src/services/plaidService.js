import { api } from './api'

export const createLinkToken = async () => {
  const { data } = await api.post('/api/plaid/link-token')
  return data.link_token
}

export const exchangePublicToken = async (publicToken) => {
  const { data } = await api.post('/api/plaid/exchange', { public_token: publicToken })
  return data
}

export const getPlaidItems = async () => {
  const { data } = await api.get('/api/plaid/items')
  return data
}

// Sync one item (pass its id) or every connected item (no argument).
export const syncPlaid = async (itemId = null) => {
  const { data } = await api.post('/api/plaid/sync', itemId ? { item_id: itemId } : {})
  return data
}

export const removePlaidItem = async (itemId) => {
  const { data } = await api.delete(`/api/plaid/items/${itemId}`)
  return data
}
