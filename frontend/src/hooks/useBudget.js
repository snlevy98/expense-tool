import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import {
  getBudgets,
  setCap,
  setLock,
  removeBudget as apiRemoveBudget,
} from '../services/budgetService'

/**
 * Envelope budget dashboard state for the selected month.
 * Payload shape: { month, year, is_closed, summary, categories, unbudgeted }
 */
export const useBudget = () => {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const selectedYear = useAppStore((s) => s.selectedYear)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchBudgets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getBudgets(selectedMonth, selectedYear)
      setData(result)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load budgets')
    } finally {
      setLoading(false)
    }
  }, [selectedMonth, selectedYear])

  useEffect(() => {
    fetchBudgets()
  }, [fetchBudgets])

  const saveCap = async (subcategoryId, amount) => {
    await setCap(subcategoryId, selectedMonth, selectedYear, amount)
    await fetchBudgets()
  }

  const toggleLock = async (subcategoryId, locked) => {
    await setLock(subcategoryId, selectedMonth, selectedYear, locked)
    await fetchBudgets()
  }

  const removeBudget = async (subcategoryId) => {
    await apiRemoveBudget(subcategoryId, selectedMonth, selectedYear)
    await fetchBudgets()
  }

  return {
    data,
    loading,
    error,
    refetch: fetchBudgets,
    saveCap,
    toggleLock,
    removeBudget,
    selectedMonth,
    selectedYear,
  }
}
