import { useState, useEffect, useCallback } from 'react'
import { AlertCircle, CheckCircle, ChevronLeft, ChevronRight, Loader2, RefreshCw, Sparkles, Trash2, XCircle } from 'lucide-react'
import { getTransactions, updateTransaction, deleteTransaction } from '../services/transactionService'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { formatDate } from '../utils/date'
import { formatCurrency } from '../utils/currency'
import { api } from '../services/api'

const PAGE_SIZE = 50

// Shared stateful logic for one row — used by both the desktop table row and
// the mobile card so behavior stays identical across the two layouts.
function useCategorizeItem(transaction, getSubcategories, onCategorized, onDeleted) {
  const [categoryId, setCategoryId] = useState(
    transaction.ai_suggested_category_id || transaction.category_id || ''
  )
  const [subcategoryId, setSubcategoryId] = useState(
    transaction.ai_suggested_subcategory_id || transaction.subcategory_id || ''
  )
  const [saved, setSaved] = useState(false)

  const subcategories = getSubcategories(categoryId)

  const handleCategoryChange = (e) => {
    setCategoryId(e.target.value)
    setSubcategoryId('')
  }

  const handleSubcategoryChange = (e) => {
    setSubcategoryId(e.target.value)
  }

  const handleDelete = useCallback(() => {
    setSaved(true)
    setTimeout(() => onDeleted(transaction.id), 150)
    deleteTransaction(transaction.id).catch((err) => console.error('Failed to delete transaction:', err))
  }, [transaction.id, onDeleted])

  const handleSave = useCallback(() => {
    if (!categoryId) return
    // Optimistic: trigger collapse animation immediately, remove after it finishes
    setSaved(true)
    setTimeout(() => onCategorized(transaction.id), 150)
    // Fire-and-forget save in the background
    updateTransaction(transaction.id, {
      category_id: categoryId || null,
      subcategory_id: subcategoryId || null,
    }).catch((err) => console.error('Failed to save category:', err))
  }, [transaction.id, categoryId, subcategoryId, onCategorized])

  return {
    categoryId, subcategoryId, saved, subcategories,
    handleCategoryChange, handleSubcategoryChange, handleSave, handleDelete,
  }
}

// ── Desktop: table row (lg and up) ──────────────────────────────────────────

function CategorizeDesktopRow({ transaction, categories, getSubcategories, onCategorized, onDeleted }) {
  const {
    categoryId, subcategoryId, saved, subcategories,
    handleCategoryChange, handleSubcategoryChange, handleSave, handleDelete,
  } = useCategorizeItem(transaction, getSubcategories, onCategorized, onDeleted)

  return (
    <tr
      className={`transition-all duration-150 origin-top ${
        saved ? 'opacity-0 scale-y-0' : 'hover:bg-slate-50'
      }`}
    >
      <td className="table-cell text-slate-500 whitespace-nowrap text-sm">
        {formatDate(transaction.transaction_date)}
      </td>
      <td className="table-cell">
        <div className="font-medium text-slate-800 text-sm">{transaction.merchant_name}</div>
        {transaction.merchant_name !== transaction.raw_description && (
          <div
            className="text-xs text-slate-400 truncate max-w-[220px]"
            title={transaction.raw_description}
          >
            {transaction.raw_description}
          </div>
        )}
      </td>
      <td className="table-cell text-sm text-slate-500">{transaction.account_name || '—'}</td>
      <td
        className={`table-cell font-semibold tabular-nums text-sm whitespace-nowrap ${
          parseFloat(transaction.amount) < 0 ? 'text-emerald-600' : 'text-slate-800'
        }`}
      >
        {formatCurrency(transaction.amount)}
      </td>

      {/* Category */}
      <td className="table-cell">
        <select
          className="input py-1 text-sm min-w-[160px]"
          value={categoryId}
          onChange={handleCategoryChange}
          disabled={saved}
        >
          <option value="">— Select Category —</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </td>

      {/* Subcategory */}
      <td className="table-cell">
        <select
          className="input py-1 text-sm min-w-[160px]"
          value={subcategoryId}
          onChange={handleSubcategoryChange}
          disabled={saved || !categoryId || subcategories.length === 0}
        >
          <option value="">— Select Subcategory —</option>
          {subcategories.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </td>

      {/* Confirm / Delete */}
      <td className="table-cell w-20">
        <div className="flex items-center gap-1">
          <button
            onClick={handleSave}
            disabled={saved || !categoryId}
            title={categoryId ? 'Save category' : 'Select a category first'}
            className={`p-1.5 rounded-full transition-colors ${
              categoryId
                ? 'text-emerald-600 hover:bg-emerald-50'
                : 'text-slate-300 cursor-not-allowed'
            }`}
          >
            <CheckCircle size={22} />
          </button>
          <button
            onClick={handleDelete}
            disabled={saved}
            title="Delete transaction"
            className="p-1.5 rounded-full transition-colors text-red-400 hover:bg-red-50 hover:text-red-600"
          >
            <XCircle size={22} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Mobile: stacked card (below lg) — everything for one transaction fits
// without horizontal scroll; category + subcategory sit side by side to
// keep the card short. ──────────────────────────────────────────────────────

function CategorizeMobileCard({ transaction, categories, getSubcategories, onCategorized, onDeleted }) {
  const {
    categoryId, subcategoryId, saved, subcategories,
    handleCategoryChange, handleSubcategoryChange, handleSave, handleDelete,
  } = useCategorizeItem(transaction, getSubcategories, onCategorized, onDeleted)

  return (
    <div
      className={`p-3 transition-all duration-150 origin-top ${
        saved ? 'opacity-0 scale-y-0' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-medium text-slate-800 text-sm truncate">{transaction.merchant_name}</div>
          {transaction.merchant_name !== transaction.raw_description && (
            <div className="text-xs text-slate-400 truncate">{transaction.raw_description}</div>
          )}
        </div>
        <div
          className={`font-semibold tabular-nums text-sm whitespace-nowrap ${
            parseFloat(transaction.amount) < 0 ? 'text-emerald-600' : 'text-slate-800'
          }`}
        >
          {formatCurrency(transaction.amount)}
        </div>
      </div>

      <div className="text-xs text-slate-400 mt-0.5 mb-2">
        {formatDate(transaction.transaction_date)} · {transaction.account_name || '—'}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <select
          className="input py-1.5 text-sm"
          value={categoryId}
          onChange={handleCategoryChange}
          disabled={saved}
        >
          <option value="">— Category —</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <select
          className="input py-1.5 text-sm"
          value={subcategoryId}
          onChange={handleSubcategoryChange}
          disabled={saved || !categoryId || subcategories.length === 0}
        >
          <option value="">— Subcategory —</option>
          {subcategories.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </div>

      <div className="flex items-stretch gap-2">
        <button
          onClick={handleSave}
          disabled={saved || !categoryId}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium transition-colors ${
            categoryId
              ? 'bg-emerald-600 text-white hover:bg-emerald-700'
              : 'bg-slate-100 text-slate-400 cursor-not-allowed'
          }`}
        >
          <CheckCircle size={16} /> Confirm
        </button>
        <button
          onClick={handleDelete}
          disabled={saved}
          title="Delete transaction"
          className="shrink-0 px-3 rounded-lg border border-red-200 text-red-500 hover:bg-red-50 transition-colors"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  )
}

function SkeletonDesktopRow() {
  return (
    <tr>
      {Array.from({ length: 7 }).map((_, j) => (
        <td key={j} className="table-cell">
          <div className="skeleton h-4 rounded w-full" />
        </td>
      ))}
    </tr>
  )
}

function SkeletonMobileCard() {
  return (
    <div className="p-3 space-y-2">
      <div className="flex justify-between gap-2">
        <div className="skeleton h-4 rounded w-2/3" />
        <div className="skeleton h-4 rounded w-16" />
      </div>
      <div className="skeleton h-3 rounded w-1/3" />
      <div className="grid grid-cols-2 gap-2">
        <div className="skeleton h-8 rounded" />
        <div className="skeleton h-8 rounded" />
      </div>
      <div className="skeleton h-8 rounded" />
    </div>
  )
}

export default function Categorize() {
  const { categories, getSubcategories } = useCategories()
  const fetchUncategorizedCount = useAppStore((s) => s.fetchUncategorizedCount)

  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)

  const [enriching, setEnriching] = useState(false)
  const [enrichResult, setEnrichResult] = useState(null)

  // Background enrichment progress polling
  const [enrichStatus, setEnrichStatus] = useState({ running: false, processed: 0, total: 0 })

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const fetchPage = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getTransactions({
        uncategorized: true,
        exclude_amazon: true,
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

  // Poll enrich-status every 15s; always check on mount
  const pollEnrichStatus = useCallback(async () => {
    try {
      const { data } = await api.get('/api/transactions/enrich-status')
      setEnrichStatus(data)
    } catch (err) {
      console.warn('Failed to fetch enrich status:', err?.response?.status, err?.message)
    }
  }, [])

  useEffect(() => {
    pollEnrichStatus()
    const interval = setInterval(pollEnrichStatus, 15000)
    return () => clearInterval(interval)
  }, [pollEnrichStatus])

  const handleCategorized = useCallback(
    (id) => {
      setTransactions((prev) => prev.filter((t) => t.id !== id))
      setTotal((prev) => Math.max(0, prev - 1))
      fetchUncategorizedCount()
    },
    [fetchUncategorizedCount]
  )

  const handleAutoEnrich = useCallback(async () => {
    setEnriching(true)
    setEnrichResult(null)
    try {
      const { data } = await api.post('/api/transactions/enrich-pending')
      setEnrichResult({ queued: data.queued, message: data.message })
      if (data.queued > 0) {
        // Poll immediately so the progress banner appears right away
        pollEnrichStatus()
        setTimeout(() => fetchPage(), 4000)
      }
    } catch (err) {
      setEnrichResult({ error: err.response?.data?.detail || 'Failed to start enrichment.' })
    } finally {
      setEnriching(false)
    }
  }, [fetchPage, pollEnrichStatus])

  const isEmpty = !loading && transactions.length === 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Categorize Transactions</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {total > 0
              ? `${total} transaction${total !== 1 ? 's' : ''} need${total === 1 ? 's' : ''} categorizing — review the AI suggestions and click ✓ to confirm`
              : 'All transactions are categorized'}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={fetchPage}
            disabled={loading}
            className="btn-secondary"
            title="Refresh transactions"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={handleAutoEnrich}
            disabled={enriching}
            className="btn-secondary"
          >
            {enriching
              ? <><Loader2 size={14} className="animate-spin" /> Enriching…</>
              : <><Sparkles size={14} /> Auto-categorize</>}
          </button>
        </div>
      </div>

      {/* Background enrichment progress banner */}
      {enrichStatus.running && (
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-indigo-50 text-indigo-700 text-sm font-medium">
          <div className="flex items-center gap-2">
            <Loader2 size={14} className="animate-spin shrink-0" />
            <span>
              Enriching in background —{' '}
              <span className="font-semibold">{enrichStatus.processed}</span>
              {' / '}
              <span className="font-semibold">{enrichStatus.total}</span>
              {' transactions processed'}
            </span>
          </div>
          {enrichStatus.total > 0 && (
            <div className="flex items-center gap-2 shrink-0">
              <div className="w-24 sm:w-32 h-1.5 bg-indigo-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                  style={{ width: `${Math.round((enrichStatus.processed / enrichStatus.total) * 100)}%` }}
                />
              </div>
              <span className="text-xs tabular-nums">
                {Math.round((enrichStatus.processed / enrichStatus.total) * 100)}%
              </span>
            </div>
          )}
        </div>
      )}

      {enrichResult && (
        <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium ${
          enrichResult.error
            ? 'bg-red-50 text-red-700'
            : enrichResult.queued === 0
            ? 'bg-slate-50 text-slate-600'
            : 'bg-indigo-50 text-indigo-700'
        }`}>
          {enrichResult.error
            ? <><AlertCircle size={14} /> {enrichResult.error}</>
            : enrichResult.queued === 0
            ? enrichResult.message || 'All transactions already have AI suggestions.'
            : <><Loader2 size={14} className="animate-spin" /> AI enrichment started for {enrichResult.queued} transaction{enrichResult.queued !== 1 ? 's' : ''} — suggestions will appear shortly.</>}
        </div>
      )}

      {isEmpty ? (
        <div className="card text-center py-16">
          <CheckCircle size={48} className="mx-auto text-emerald-500 mb-4" />
          <h2 className="text-xl font-semibold text-slate-800 mb-2">All caught up!</h2>
          <p className="text-slate-500">Every transaction has a category assigned.</p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          {/* Desktop: full table (lg and up) */}
          <div className="hidden lg:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="table-header">Date</th>
                  <th className="table-header">Merchant</th>
                  <th className="table-header">Account</th>
                  <th className="table-header">Amount</th>
                  <th className="table-header">Category</th>
                  <th className="table-header">Subcategory</th>
                  <th className="table-header w-12" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading
                  ? Array.from({ length: 8 }).map((_, i) => <SkeletonDesktopRow key={i} />)
                  : transactions.map((tx) => (
                      <CategorizeDesktopRow
                        key={tx.id}
                        transaction={tx}
                        categories={categories}
                        getSubcategories={getSubcategories}
                        onCategorized={handleCategorized}
                        onDeleted={handleCategorized}
                      />
                    ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: stacked cards (below lg) — no horizontal scroll, one
              transaction's full context fits in a single glance */}
          <div className="lg:hidden divide-y divide-slate-100">
            {loading
              ? Array.from({ length: 5 }).map((_, i) => <SkeletonMobileCard key={i} />)
              : transactions.map((tx) => (
                  <CategorizeMobileCard
                    key={tx.id}
                    transaction={tx}
                    categories={categories}
                    getSubcategories={getSubcategories}
                    onCategorized={handleCategorized}
                    onDeleted={handleCategorized}
                  />
                ))}
          </div>

          {totalPages > 1 && (
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 border-t border-slate-200">
              <p className="text-sm text-slate-500">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of{' '}
                {total}
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
