import { useState, useEffect, useCallback } from 'react'
import { getTransactions, updateTransaction, deleteTransaction } from '../services/transactionService'

const DEFAULT_FILTERS = {
  account_id: '',
  category_id: '',
  subcategory_id: '',
  date_from: '',
  date_to: '',
  amount_min: '',
  amount_max: '',
  is_recurring: '',
  search: '',
}

const PAGE_SIZE = 50

export const useTransactions = () => {
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [sortBy, setSortBy] = useState('date')
  const [sortDir, setSortDir] = useState('desc')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)

  const buildParams = useCallback(() => {
    const params = {
      skip: page * PAGE_SIZE,
      limit: PAGE_SIZE,
      sort_by: sortBy,
      sort_dir: sortDir,
    }
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== '' && v !== null && v !== undefined) params[k] = v
    })
    return params
  }, [filters, sortBy, sortDir, page])

  const fetchTransactions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getTransactions(buildParams())
      if (Array.isArray(result)) {
        setTransactions(result)
        setTotal(result.length)
      } else {
        setTransactions(result.items ?? result.data ?? [])
        setTotal(result.total ?? 0)
      }
    } catch (err) {
      setError(err.message || 'Failed to load transactions')
    } finally {
      setLoading(false)
    }
  }, [buildParams])

  useEffect(() => {
    fetchTransactions()
  }, [fetchTransactions])

  const updateFilter = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
    setPage(0)
  }

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS)
    setPage(0)
  }

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(column)
      setSortDir('asc')
    }
    setPage(0)
  }

  const editTransaction = async (id, data) => {
    const updated = await updateTransaction(id, data)
    setTransactions((prev) => prev.map((t) => (t.id === id ? { ...t, ...updated } : t)))
    return updated
  }

  const removeTransaction = async (id) => {
    await deleteTransaction(id)
    setTransactions((prev) => prev.filter((t) => t.id !== id))
    setTotal((prev) => prev - 1)
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return {
    transactions,
    loading,
    error,
    filters,
    sortBy,
    sortDir,
    page,
    total,
    totalPages,
    pageSize: PAGE_SIZE,
    updateFilter,
    resetFilters,
    handleSort,
    editTransaction,
    removeTransaction,
    refetch: fetchTransactions,
    setPage,
    currentFilters: buildParams(),
  }
}
