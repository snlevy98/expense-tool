import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, Copy, Loader2, Pencil } from 'lucide-react'
import MonthSwitcher from '../components/MonthSwitcher'
import { useBudget } from '../hooks/useBudget'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'

// ── Editable amount cell ────────────────────────────────────────────────────

function AmountCell({ value, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)

  const commit = async () => {
    setSaving(true)
    try {
      await onSave(parseFloat(draft) || 0)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const cancel = () => {
    setEditing(false)
    setDraft(value)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') commit()
    if (e.key === 'Escape') cancel()
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="number"
          step="0.01"
          min="0"
          className="input w-32 py-1 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
        />
        <button
          onClick={commit}
          disabled={saving}
          className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded transition-colors"
        >
          <Check size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <span className="tabular-nums font-medium">{formatCurrency(value)}</span>
      <button
        onClick={() => { setDraft(value); setEditing(true) }}
        className="p-1 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
      >
        <Pencil size={14} />
      </button>
    </div>
  )
}

// ── Editable pool % ─────────────────────────────────────────────────────────

function PoolPctCell({ value, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(Math.round(value * 100))
  const [saving, setSaving] = useState(false)

  const commit = async () => {
    const pct = Math.max(1, Math.min(100, parseInt(draft) || 80))
    setSaving(true)
    try {
      await onSave(pct / 100)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') commit()
    if (e.key === 'Escape') { setEditing(false); setDraft(Math.round(value * 100)) }
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <input
          type="number"
          min="1"
          max="100"
          className="input w-16 py-0.5 text-sm text-center"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={commit}
          autoFocus
        />
        <span className="text-slate-500">%</span>
      </span>
    )
  }

  return (
    <button
      onClick={() => { setDraft(Math.round(value * 100)); setEditing(true) }}
      className="inline-flex items-center gap-1 font-semibold text-indigo-700 hover:underline"
      disabled={saving}
    >
      {Math.round(value * 100)}%
      <Pencil size={12} className="text-indigo-400" />
    </button>
  )
}

// ── Category row with subcategories (expandable) ───────────────────────────

function CategoryWithSubsRow({ catBudget, onSave }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <>
      {/* Category header — read-only total, click to expand/collapse */}
      <tr
        className="bg-slate-50 hover:bg-slate-100 cursor-pointer select-none"
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="table-cell">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 shrink-0">
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
            <span
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: catBudget.category_color || '#94a3b8' }}
            />
            <span className="font-semibold text-slate-700">{catBudget.category_name}</span>
          </div>
        </td>
        <td className="table-cell tabular-nums font-semibold text-slate-700">
          {formatCurrency(catBudget.total_amount)}
        </td>
        <td className="table-cell text-xs text-slate-400 italic">
          sum of subcategories
        </td>
      </tr>

      {/* Subcategory rows */}
      {expanded &&
        catBudget.subcategory_budgets.map((sub) => (
          <tr key={sub.subcategory_id} className="hover:bg-slate-50">
            <td className="table-cell pl-10 text-slate-600">
              {sub.subcategory_name}
            </td>
            <td className="table-cell">
              <AmountCell
                value={parseFloat(sub.amount) || 0}
                onSave={(amount) =>
                  onSave(sub.category_id, sub.subcategory_id, amount)
                }
              />
            </td>
            <td className="table-cell" />
          </tr>
        ))}
    </>
  )
}

// ── Category row without subcategories (directly editable) ─────────────────

function CategoryDirectRow({ catBudget, onSave }) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="table-cell">
        <div className="flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: catBudget.category_color || '#94a3b8' }}
          />
          <span className="font-medium text-slate-800">{catBudget.category_name}</span>
        </div>
      </td>
      <td className="table-cell">
        <AmountCell
          value={parseFloat(catBudget.total_amount) || 0}
          onSave={(amount) => onSave(catBudget.category_id, null, amount)}
        />
      </td>
      <td className="table-cell" />
    </tr>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export default function Budgets() {
  const setMonth = useAppStore((s) => s.setMonth)
  const {
    budgets,
    poolInfo,
    loading,
    error,
    saveBudget,
    savePoolPct,
    fillFromLastMonth,
    selectedMonth,
    selectedYear,
  } = useBudget()

  const [filling, setFilling] = useState(false)
  const [fillResult, setFillResult] = useState(null)

  const handleFill = async () => {
    setFilling(true)
    setFillResult(null)
    try {
      const result = await fillFromLastMonth()
      setFillResult(result.copied)
    } catch {
      setFillResult(-1)
    } finally {
      setFilling(false)
    }
  }

  const isOverBudget = poolInfo.leftover < 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Budgets</h1>
          <p className="text-slate-500 text-sm mt-0.5">Manage monthly category budgets</p>
        </div>
        <MonthSwitcher month={selectedMonth} year={selectedYear} onChange={setMonth} />
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Pool Summary Panel */}
      <div className="card space-y-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="text-slate-600">
            Budget pool:{' '}
            <PoolPctCell value={poolInfo.pool_pct} onSave={savePoolPct} />
            {' '}of last month's income{' '}
            <span className="text-slate-500">({formatCurrency(poolInfo.last_month_income)})</span>
            {' '}={' '}
            <span className="font-semibold text-slate-800">{formatCurrency(poolInfo.pool_amount)}</span>
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span className="text-slate-600">
            Allocated:{' '}
            <span className="font-semibold text-slate-800">{formatCurrency(poolInfo.allocated)}</span>
          </span>
          <span className={isOverBudget ? 'text-red-600 font-semibold' : 'text-slate-600'}>
            Leftover:{' '}
            <span className={`font-semibold ${isOverBudget ? 'text-red-600' : 'text-emerald-700'}`}>
              {formatCurrency(poolInfo.leftover)}
            </span>
            {isOverBudget && (
              <span className="ml-1 text-xs text-red-500">(over budget!)</span>
            )}
          </span>

          <button
            onClick={handleFill}
            disabled={filling}
            className="btn-secondary ml-auto"
          >
            {filling
              ? <><Loader2 size={14} className="animate-spin" /> Filling…</>
              : <><Copy size={14} /> Fill from Last Month</>}
          </button>
        </div>

        {fillResult !== null && (
          <p className="text-xs text-slate-500">
            {fillResult === -1
              ? 'Failed to copy budgets from last month.'
              : fillResult === 0
              ? 'No budgets found in the previous month to copy.'
              : `Copied ${fillResult} budget${fillResult !== 1 ? 's' : ''} from last month.`}
          </p>
        )}
      </div>

      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center">
          <h2 className="font-semibold text-slate-700">Category Budgets</h2>
          <span className="text-sm text-slate-500">
            Total:{' '}
            <span className="font-semibold text-slate-800">
              {formatCurrency(poolInfo.allocated)}
            </span>
          </span>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header">Category / Subcategory</th>
              <th className="table-header">This Month</th>
              <th className="table-header w-40" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              [...Array(6)].map((_, i) => (
                <tr key={i}>
                  {[...Array(3)].map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 skeleton rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : budgets.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-slate-400">
                  No categories found. Add categories in Settings.
                </td>
              </tr>
            ) : (
              budgets.map((catBudget) =>
                catBudget.has_subcategories ? (
                  <CategoryWithSubsRow
                    key={catBudget.category_id}
                    catBudget={catBudget}
                    onSave={saveBudget}
                  />
                ) : (
                  <CategoryDirectRow
                    key={catBudget.category_id}
                    catBudget={catBudget}
                    onSave={saveBudget}
                  />
                )
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
