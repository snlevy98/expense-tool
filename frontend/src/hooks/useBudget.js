import { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import {
  getBudgets,
  upsertBudget,
  updateBudgetDefault,
  updateBudgetSettings,
  fillFromLastMonth as apiFillFromLastMonth,
} from '../services/budgetService'

export const useBudget = () => {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const selectedYear = useAppStore((s) => s.selectedYear)

  const [budgets, setBudgets] = useState([])
  const [poolInfo, setPoolInfo] = useState({
    pool_pct: 0.8,
    pool_amount: 0,
    last_month_income: 0,
    allocated: 0,
    leftover: 0,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchBudgets = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getBudgets(selectedMonth, selectedYear)
      // data is BudgetListResponse: { budgets, pool_pct, pool_amount, ... }
      setBudgets(Array.isArray(data) ? data : (data.budgets ?? []))
      if (data && !Array.isArray(data)) {
        setPoolInfo({
          pool_pct: parseFloat(data.pool_pct ?? 0.8),
          pool_amount: parseFloat(data.pool_amount ?? 0),
          last_month_income: parseFloat(data.last_month_income ?? 0),
          allocated: parseFloat(data.allocated ?? 0),
          leftover: parseFloat(data.leftover ?? 0),
        })
      }
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
    setBudgets((prev) => {
      const updated = prev.map((catBudget) => {
        if (String(catBudget.category_id) !== String(categoryId)) return catBudget

        if (!subcategoryId) {
          return { ...catBudget, total_amount: amount }
        }

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

      // Recompute allocated/leftover from updated budgets
      const newAllocated = updated.reduce(
        (sum, b) => sum + parseFloat(b.total_amount || 0),
        0
      )
      setPoolInfo((p) => ({
        ...p,
        allocated: newAllocated,
        leftover: p.pool_amount - newAllocated,
      }))

      return updated
    })

    return saved
  }

  const saveDefault = async (categoryId, defaultAmount) => {
    return await updateBudgetDefault(categoryId, defaultAmount)
  }

  /**
   * Update pool_pct. Optimistically updates poolInfo; refetches to get new pool_amount.
   */
  const savePoolPct = async (pct) => {
    await updateBudgetSettings(pct)
    // Refetch to get updated pool_amount based on last month's income × new pct
    await fetchBudgets()
  }

  /**
   * Copy budget amounts from the previous month into the current month.
   */
  const fillFromLastMonth = async () => {
    const result = await apiFillFromLastMonth(selectedMonth, selectedYear)
    await fetchBudgets()
    return result
  }

  return {
    budgets,
    poolInfo,
    loading,
    error,
    refetch: fetchBudgets,
    saveBudget,
    saveDefault,
    savePoolPct,
    fillFromLastMonth,
    selectedMonth,
    selectedYear,
  }
}
