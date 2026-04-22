import { useState, useEffect, useCallback } from 'react'
import { CheckCircle, ChevronLeft, ChevronRight, Tag } from 'lucide-react'
import { getTransactions, updateTransaction } from '../services/transactionService'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { formatDate } from '../utils/date'
import { formatCurrency } from '../utils/currency'

const PAGE_SIZE = 50

function InlineCategoryRow({ transaction, categories, getSubcategories, onCategorized }) {
  const [categoryId, setCategoryId] = useState(transaction.category_id || '')
  const [subcategoryId, setSubcategoryId] = useState(transaction.subcategory_id || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const subcategories = getSubcategories(categoryId)

  const save = useCallback(async (catId, subcatId) => {
    if (!catId) return
    setSaving(true)
    try {
      await updateTransaction(transaction.id, {
        category_id: catId || null,
        subcategory_id: subcatId || null,
      })
      setSaved(true)
      setTimeout(() => onCategorized(transaction.id), 600)
    } catch (err) {
      console.error('Failed to update:', err)
      setSaving(false)
    }
  }, [transaction.id, onCategorized])

  const handleCategoryChange = (e) => {
    const newCatId = e.target.value
    setCategoryId(newCatId)
    setSubcategoryId('')
    // Don't save yet — wait for subcategory selection or explicit Save click
  }

  const handleSubcategoryChange = (e) => {
    const newSubId = e.target.value
    setSubcategoryId(newSubId)
    save(categoryId, newSubId)
  }

  const handleSave = () => {
    save(categoryId, subcategoryId)
  }

  const hasSubcategories = subcategories.length > 0

  return (
    <tr className={`transition-all duration-500 ${saved ? 'opacity-0 bg-emerald-50' : 'hover:bg-slate-50'}`}>
      <td className="table-cell text-slate-500 whitespace-nowrap text-sm">
        {formatDate(transaction.transaction_date)}
      </td>
      <td className="table-cell">
        <div className="font-medium text-slate-800 text-sm">{transaction.merchant_name}</div>
        {transaction.merchant_name !== transaction.raw_description && (
          <div className="text-xs text-slate-400 truncate max-w-[220px]" title={transaction.raw_description}>
            {transaction.raw_description}
          </div>
        )}
      </td>
      <td className="table-cell text-sm text-slate-500">{transaction.account_name || '—'}</td>
      <td className={`table-cell font-semibold tabular-nums text-sm whitespace-nowrap ${
        parseFloat(transaction.amount) < 0 ? 'text-emerald-600' : 'text-slate-800'
      }`}>
        {formatCurrency(transaction.amount)}
      </td>
      <td className="table-cell">
        {saved ? (
          <span className="flex items-center gap-1 text-emerald-600 text-sm font-medium">
            <CheckCircle size={14} /> Saved
          </span>
        ) : (
          <select
            className="input py-1 text-sm min-w-[160px]"
            value={categoryId}
            onChange={handleCategoryChange}
            disabled={saving}
          >
            <option value="">— Select Category —</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}
      </td>
      <td className="table-cell">
        {!saved && (
          hasSubcategories ? (
            <select
              className="input py-1 text-sm min-w-[160px]"
              value={subcategoryId}
              onChange={handleSubcategoryChange}
              disabled={saving || !categoryId}
            >
              <option value="">— Select Subcategory —</option>
              {subcategories.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          ) : (
            <button
              className="btn-primary py-1 px-3 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={handleSave}
              disabled={saving || !categoryId}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          )
        )}
      </td>
    </tr>
  )
}

export default function Categorize() {
  const { categories, getSubcategories } = useCategories()
  const fetchUncategorizedCount = useAppStore((s) => s.fetchUncategorizedCount)

  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const fetchPage = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getTransactions({
        uncategorized: true,
        sort_by: 'date',
        sort_dir: 'desc',
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      })
      const items = Array.isArray(data) ? data : (data.items ?? [])
      setTransactions(items)
      setTotal(typeof data.total === 'number' ? data.total : items.length + page * PAGE_SIZE)
    } catch (err) {
      console.error('Failed to load uncategorized transactions:', err)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    fetchPage()
  }, [fetchPage])

  const handleCategorized = useCallback((id) => {
    setTransactions((prev) => prev.filter((t) => t.id !== id))
    setTotal((prev) => Math.max(0, prev - 1))
    fetchUncategorizedCount()
  }, [fetchUncategorizedCount])

  const isEmpty = !loading && transactions.length === 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Categorize Transactions</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          {total > 0
            ? `${total} transaction${total !== 1 ? 's' : ''} need${total === 1 ? 's' : ''} a category — select one to auto-save`
            : 'All transactions are categorized'}
        </p>
      </div>

      {isEmpty ? (
        <div className="card text-center py-16">
          <CheckCircle size={48} className="mx-auto text-emerald-500 mb-4" />
          <h2 className="text-xl font-semibold text-slate-800 mb-2">All caught up!</h2>
          <p className="text-slate-500">Every transaction has a category assigned.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="table-header">Date</th>
                  <th className="table-header">Merchant</th>
                  <th className="table-header">Account</th>
                  <th className="table-header">Amount</th>
                  <th className="table-header">Category</th>
                  <th className="table-header">Subcategory</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading
                  ? Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 6 }).map((_, j) => (
                          <td key={j} className="table-cell">
                            <div className="skeleton h-4 rounded w-full" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : transactions.map((tx) => (
                      <InlineCategoryRow
                        key={tx.id}
                        transaction={tx}
                        categories={categories}
                        getSubcategories={getSubcategories}
                        onCategorized={handleCategorized}
                      />
                    ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200">
              <p className="text-sm text-slate-500">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="btn-secondary py-1.5 px-2"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="flex items-center px-3 text-sm text-slate-600">
                  {page + 1} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="btn-secondary py-1.5 px-2"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
