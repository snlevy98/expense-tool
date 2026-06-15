import { create } from 'zustand'
import { getCategories } from '../services/categoryService'
import { getAccounts } from '../services/accountService'
import { api } from '../services/api'

const now = new Date()

// Phase timer for the Amazon scrape, kept at module scope so it survives the
// Amazon component unmounting/remounting while a pull is in flight.
let amazonPhaseTimer = null

export const useAppStore = create((set, get) => ({
  categories: [],
  accounts: [],
  selectedMonth: now.getMonth() + 1,
  selectedYear: now.getFullYear(),
  uncategorizedCount: 0,
  amazonUncategorizedCount: 0,

  // Amazon "Pull Order History" lifecycle — lives in the store so the in-progress
  // state and the result persist across tab navigation within the session.
  amazonPullStatus: 'idle', // 'idle' | 'opening' | 'scraping'
  amazonPullError: null,
  amazonPullResult: null,

  fetchCategories: async () => {
    try {
      const data = await getCategories()
      set({ categories: data })
    } catch (err) {
      console.error('Failed to fetch categories:', err)
    }
  },

  fetchAccounts: async () => {
    try {
      const data = await getAccounts()
      set({ accounts: data })
    } catch (err) {
      console.error('Failed to fetch accounts:', err)
    }
  },

  fetchUncategorizedCount: async () => {
    try {
      const { data } = await api.get('/api/transactions/uncategorized-count', {
        params: { exclude_amazon: true },
      })
      set({ uncategorizedCount: data.count })
    } catch {
      // silently ignore
    }
  },

  fetchAmazonUncategorizedCount: async () => {
    try {
      const { data } = await api.get('/api/amazon/uncategorized-count')
      set({ amazonUncategorizedCount: data.count })
    } catch {
      // silently ignore
    }
  },

  // Trigger the backend scraper and import. Returns the analysis on success;
  // re-throws on failure (the error is also stored for the UI to render).
  pullAmazonOrders: async ({ months = null, year = null } = {}) => {
    if (amazonPhaseTimer) clearTimeout(amazonPhaseTimer)
    set({ amazonPullStatus: 'opening', amazonPullError: null, amazonPullResult: null })

    // After 5s, advance the message — but only if we're still on the opening phase.
    amazonPhaseTimer = setTimeout(() => {
      if (get().amazonPullStatus === 'opening') set({ amazonPullStatus: 'scraping' })
    }, 5000)

    try {
      const body = {}
      if (months != null) body.months = months
      if (year != null) body.year = year
      const { data } = await api.post('/api/amazon/pull-and-import', body)
      set({ amazonPullStatus: 'idle', amazonPullResult: data })
      return data
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Pull failed'
      set({ amazonPullStatus: 'idle', amazonPullError: detail })
      throw err
    } finally {
      if (amazonPhaseTimer) {
        clearTimeout(amazonPhaseTimer)
        amazonPhaseTimer = null
      }
    }
  },

  clearAmazonPull: () =>
    set({ amazonPullStatus: 'idle', amazonPullError: null, amazonPullResult: null }),

  setMonth: (month, year) => {
    set({ selectedMonth: month, selectedYear: year })
  },
}))
