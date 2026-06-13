import { useState } from 'react'
import { Download, RefreshCw, ChevronLeft, ChevronRight, X, Search } from 'lucide-react'
import TransactionTable from '../components/TransactionTable'
import EditTransactionModal from '../components/EditTransactionModal'
import { useTransactions } from '../hooks/useTransactions'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { exportTransactions } from '../services/transactionService'

export default function Transactions() {
  const {
    transactions, loading, error, filters, sortBy, sortDir,
    page, total, totalPages, pageSize,
    updateFilter, resetFilters, handleSort,
    editTransaction, removeTransaction, toggleExclusion, refetch, setPage,
    currentFilters,
  } = useTransactions()

  const { categories, getSubcategories } = useCategories()
  const accounts = useAppStore((s) => s.accounts)

  const [editingTx, setEditingTx] = useState(null)
  const [exporting, setExporting] = useState(false)

  const subcategories = getSubcategories(filters.category_id)

  const handleExport = async () => {
    setExporting(true)
    try {
      await exportTransactions(currentFilters)
    } finally {
      setExporting(false)
    }
  }

  const handleSave = async (id, data) => {
    await editTransaction(id, data)
    setEditingTx(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Transactions</h1>
          <p className="text-slate-500 text-sm mt-0.5">{total} total transactions</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <button onClick={refetch} className="btn-secondary" disabled={loading}>
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
          <button onClick={handleExport} className="btn-secondary" disabled={exporting}>
            <Download size={15} />
            <span className="hidden sm:inline">{exporting ? 'Exporting...' : 'Export CSV'}</span>
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4">
        {/* Search bar */}
        <div className="relative mb-4">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input
            type="text"
            className="input pl-9"
            placeholder="Search by merchant or description…"
            value={filters.search}
            onChange={(e) => updateFilter('search', e.target.value)}
          />
          {filters.search && (
            <button
              onClick={() => updateFilter('search', '')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          <div>
            <label className="label">Account</label>
            <select
              className="input"
              value={filters.account_id}
              onChange={(e) => updateFilter('account_id', e.target.value)}
            >
              <option value="">— All Accounts —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Category</label>
            <select
              className="input"
              value={filters.category_id}
              onChange={(e) => { updateFilter('category_id', e.target.value); updateFilter('subcategory_id', '') }}
            >
              <option value="">— All Categories —</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Subcategory</label>
            <select
              className="input"
              value={filters.subcategory_id}
              onChange={(e) => updateFilter('subcategory_id', e.target.value)}
              disabled={!filters.category_id || subcategories.length === 0}
            >
              <option value="">— All —</option>
              {subcategories.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Recurring</label>
            <select
              className="input"
              value={filters.is_recurring}
              onChange={(e) => updateFilter('is_recurring', e.target.value)}
            >
              <option value="">— All —</option>
              <option value="true">Recurring Only</option>
              <option value="false">Non-Recurring</option>
            </select>
          </div>

          <div>
            <label className="label">Date From</label>
            <input
              type="date"
              className="input"
              value={filters.date_from}
              onChange={(e) => updateFilter('date_from', e.target.value)}
            />
          </div>

          <div>
            <label className="label">Date To</label>
            <input
              type="date"
              className="input"
              value={filters.date_to}
              onChange={(e) => updateFilter('date_to', e.target.value)}
            />
          </div>

          <div>
            <label className="label">Min Amount</label>
            <input
              type="number"
              step="0.01"
              className="input"
              value={filters.amount_min}
              onChange={(e) => updateFilter('amount_min', e.target.value)}
              placeholder="0.00"
            />
          </div>

          <div>
            <label className="label">Max Amount</label>
            <input
              type="number"
              step="0.01"
              className="input"
              value={filters.amount_max}
              onChange={(e) => updateFilter('amount_max', e.target.value)}
              placeholder="9999.99"
            />
          </div>
        </div>

        <div className="mt-3 flex justify-end">
          <button onClick={resetFilters} className="btn-secondary text-xs py-1.5 px-3">
            <X size={13} />
            Clear Filters
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <TransactionTable
          transactions={transactions}
          onEdit={setEditingTx}
          onDelete={removeTransaction}
          onToggleExclusion={toggleExclusion}
          loading={loading}
          sortBy={sortBy}
          sortDir={sortDir}
          onSort={handleSort}
        />

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200">
            <p className="text-sm text-slate-500">
              Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}
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

      {editingTx && (
        <EditTransactionModal
          transaction={editingTx}
          onSave={handleSave}
          onClose={() => setEditingTx(null)}
        />
      )}
    </div>
  )
}
