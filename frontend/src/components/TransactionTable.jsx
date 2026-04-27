import { useState } from 'react'
import { ChevronUp, ChevronDown, Pencil, Trash2 } from 'lucide-react'
import { formatDate } from '../utils/date'
import { formatCurrency } from '../utils/currency'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'

function SortIcon({ column, sortBy, sortDir }) {
  if (sortBy !== column) return <ChevronUp size={14} className="text-slate-300" />
  return sortDir === 'asc' ? (
    <ChevronUp size={14} className="text-indigo-600" />
  ) : (
    <ChevronDown size={14} className="text-indigo-600" />
  )
}

function SkeletonRow() {
  return (
    <tr>
      {[...Array(8)].map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 skeleton rounded" style={{ width: `${60 + (i * 13) % 40}%` }} />
        </td>
      ))}
    </tr>
  )
}

export default function TransactionTable({
  transactions,
  onEdit,
  onDelete,
  loading,
  sortBy,
  sortDir,
  onSort,
}) {
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const { findCategory, findSubcategory } = useCategories()
  const accounts = useAppStore((s) => s.accounts)

  const findAccount = (id) => accounts.find((a) => a.id === id)

  const columns = [
    { key: 'transaction_date', label: 'Date' },
    { key: 'raw_description', label: 'Description', sortable: false },
    { key: 'merchant_name', label: 'Merchant' },
    { key: 'category_id', label: 'Category', sortable: false },
    { key: 'subcategory_id', label: 'Subcategory', sortable: false },
    { key: 'account_id', label: 'Account', sortable: false },
    { key: 'amount', label: 'Amount' },
    { key: 'actions', label: '', sortable: false },
  ]

  const handleDeleteClick = (id) => {
    if (confirmDeleteId === id) {
      onDelete(id)
      setConfirmDeleteId(null)
    } else {
      setConfirmDeleteId(id)
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`table-header ${col.sortable !== false && onSort ? 'cursor-pointer select-none hover:bg-slate-100' : ''}`}
                onClick={col.sortable !== false && onSort ? () => onSort(col.key) : undefined}
              >
                <div className="flex items-center gap-1">
                  {col.label}
                  {col.sortable !== false && onSort && (
                    <SortIcon column={col.key} sortBy={sortBy} sortDir={sortDir} />
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {loading ? (
            [...Array(8)].map((_, i) => <SkeletonRow key={i} />)
          ) : transactions.length === 0 ? (
            <tr>
              <td colSpan={8} className="px-4 py-12 text-center text-slate-400 text-sm">
                No transactions found.
              </td>
            </tr>
          ) : (
            transactions.map((tx) => {
              const category = findCategory(tx.category_id)
              const subcategory = tx.subcategory_id
                ? findSubcategory(tx.category_id, tx.subcategory_id)
                : null
              const account = findAccount(tx.account_id)
              const amount = parseFloat(tx.amount)
              const isCredit = amount < 0

              return (
                <tr key={tx.id} className="hover:bg-slate-50 transition-colors">
                  <td className="table-cell text-slate-500 whitespace-nowrap">{formatDate(tx.transaction_date)}</td>
                  <td className="table-cell text-slate-500 max-w-[200px]">
                    <span
                      className="block truncate text-xs"
                      title={tx.raw_description}
                    >
                      {tx.raw_description || '—'}
                    </span>
                  </td>
                  <td className="table-cell font-medium text-slate-800">
                    {tx.merchant_name || '—'}
                    {tx.is_recurring && (
                      <span className="ml-2 text-xs bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded">
                        Recurring
                      </span>
                    )}
                  </td>
                  <td className="table-cell">
                    {category ? (
                      <div className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: category.color || '#94a3b8' }}
                        />
                        <span>{category.name}</span>
                      </div>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="table-cell text-slate-500">
                    {subcategory?.name ?? '—'}
                  </td>
                  <td className="table-cell text-slate-500">
                    {account?.name ?? '—'}
                  </td>
                  <td className={`table-cell font-medium tabular-nums ${isCredit ? 'text-emerald-600' : 'text-slate-800'}`}>
                    {isCredit ? '+' : ''}{formatCurrency(Math.abs(amount))}
                  </td>
                  <td className="table-cell">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => onEdit(tx)}
                        className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                        title="Edit"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => handleDeleteClick(tx.id)}
                        className={`p-1.5 rounded transition-colors ${
                          confirmDeleteId === tx.id
                            ? 'text-white bg-red-500 hover:bg-red-600'
                            : 'text-slate-400 hover:text-red-500 hover:bg-red-50'
                        }`}
                        title={confirmDeleteId === tx.id ? 'Click again to confirm' : 'Delete'}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
