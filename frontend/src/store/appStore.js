import { create } from 'zustand'
import { getCategories } from '../services/categoryService'
import { getAccounts } from '../services/accountService'
import { api } from '../services/api'

const now = new Date()

export const useAppStore = create((set) => ({
  categories: [],
  accounts: [],
  selectedMonth: now.getMonth() + 1,
  selectedYear: now.getFullYear(),
  uncategorizedCount: 0,
  amazonUncategorizedCount: 0,

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

  setMonth: (month, year) => {
    set({ selectedMonth: month, selectedYear: year })
  },
}))
