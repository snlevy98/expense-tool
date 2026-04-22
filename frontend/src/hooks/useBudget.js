import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import { getBudgets, upsertBudget, updateBudgetDefault } from '../services/budgetService'

export const useBudget = () => {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const selectedYear = useAppStore((s) => s.selectedYear)

  const [budgets, setBudgets] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchBudgets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getBudgets(selectedMonth, selectedYear)
      setBudgets(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.message || 'Failed to load budgets')
    } finally {
      setLoading(false)
    }
  }, [selectedMonth, selectedYear])

  useEffect(() => {
    fetchBudgets()
  }, [fetchBudgets])

  const saveBudget = async (categoryId, amount) => {
    const saved = await upsertBudget({
      category_id: categoryId,
      month: selectedMonth,
      year: selectedYear,
      amount,
    })
    setBudgets((prev) => {
      const idx = prev.findIndex((b) => b.category_id === categoryId)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...saved }
        return next
      }
      return [...prev, saved]
    })
    return saved
  }

  const saveDefault = async (categoryId, defaultAmount) => {
    const saved = await updateBudgetDefault(categoryId, defaultAmount)
    return saved
  }

  return {
    budgets,
    loading,
    error,
    refetch: fetchBudgets,
    saveBudget,
    saveDefault,
    selectedMonth,
    selectedYear,
  }
}
