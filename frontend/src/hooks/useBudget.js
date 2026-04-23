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

  /**
   * Save a budget amount.
   * @param {string} categoryId
   * @param {string|null} subcategoryId  null for direct category budgets
   * @param {number} amount
   */
  const saveBudget = async (categoryId, subcategoryId, amount) => {
    const saved = await upsertBudget({
      category_id: categoryId,
      subcategory_id: subcategoryId ?? null,
      month: selectedMonth,
      year: selectedYear,
      amount,
    })

    // Optimistically update local state
    setBudgets((prev) =>
      prev.map((catBudget) => {
        if (String(catBudget.category_id) !== String(categoryId)) return catBudget

        if (!subcategoryId) {
          // Direct category budget update
          return { ...catBudget, total_amount: amount }
        }

        // Subcategory budget update — recalculate category total
        const newSubs = catBudget.subcategory_budgets.map((sub) =>
          String(sub.subcategory_id) === String(subcategoryId)
            ? { ...sub, amount }
            : sub
        )
        const newTotal = newSubs.reduce(
          (sum, s) => sum + parseFloat(s.amount || 0),
          0
        )
        return { ...catBudget, subcategory_budgets: newSubs, total_amount: newTotal }
      })
    )

    return saved
  }

  const saveDefault = async (categoryId, defaultAmount) => {
    return await updateBudgetDefault(categoryId, defaultAmount)
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
