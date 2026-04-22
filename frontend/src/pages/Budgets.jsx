import { useState } from 'react'
import { Check, Pencil } from 'lucide-react'
import MonthSwitcher from '../components/MonthSwitcher'
import { useBudget } from '../hooks/useBudget'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'

function BudgetRow({ category, budget, onSave }) {
  const [editing, setEditing] = useState(false)
  const [amount, setAmount] = useState(budget?.amount ?? budget?.default_amount ?? 0)
  const [defaultAmount, setDefaultAmount] = useState(budget?.default_amount ?? 0)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(category.id, parseFloat(amount) || 0)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSave()
    if (e.key === 'Escape') setEditing(false)
  }

  const currentAmount = budget?.amount ?? budget?.default_amount ?? 0

  return (
    <tr className="hover:bg-slate-50">
      <td className="table-cell">
        <div className="flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: category.color || '#94a3b8' }}
          />
          <span className="font-medium text-slate-800">{category.name}</span>
        </div>
      </td>
      <td className="table-cell text-slate-500 tabular-nums">
        {formatCurrency(budget?.default_amount ?? 0)}
      </td>
      <td className="table-cell">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              className="input w-32 py-1 text-sm"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              onKeyDown={handleKeyDown}
              autoFocus
            />
            <button
              onClick={handleSave}
              disabled={saving}
              className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
            >
              <Check size={16} />
            </button>
          </div>
        ) : (
          <span className="tabular-nums font-medium">{formatCurrency(currentAmount)}</span>
        )}
      </td>
      <td className="table-cell">
        {!editing && (
          <button
            onClick={() => { setAmount(currentAmount); setEditing(true) }}
            className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
          >
            <Pencil size={15} />
          </button>
        )}
      </td>
    </tr>
  )
}

export default function Budgets() {
  const setMonth = useAppStore((s) => s.setMonth)
  const { categories } = useCategories()
  const { budgets, loading, error, saveBudget, selectedMonth, selectedYear } = useBudget()

  const getBudgetForCategory = (categoryId) => {
    return budgets.find((b) => b.category_id === categoryId) ?? null
  }

  const totalBudget = budgets.reduce((sum, b) => sum + (b.amount ?? b.default_amount ?? 0), 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Budgets</h1>
          <p className="text-slate-500 text-sm mt-0.5">Manage monthly category budgets</p>
        </div>
        <MonthSwitcher month={selectedMonth} year={selectedYear} onChange={setMonth} />
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
          <h2 className="font-semibold text-slate-700">Category Budgets</h2>
          <span className="text-sm text-slate-500">
            Total: <span className="font-semibold text-slate-800">{formatCurrency(totalBudget)}</span>
          </span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header">Category</th>
              <th className="table-header">Default Budget</th>
              <th className="table-header">This Month</th>
              <th className="table-header w-16" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(4)].map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 skeleton rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : categories.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-400">
                  No categories found. Add categories in Settings.
                </td>
              </tr>
            ) : (
              categories.map((cat) => (
                <BudgetRow
                  key={cat.id}
                  category={cat}
                  budget={getBudgetForCategory(cat.id)}
                  onSave={saveBudget}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
