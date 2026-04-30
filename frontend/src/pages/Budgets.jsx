import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, Copy, Loader2, Pencil, Sparkles, X } from 'lucide-react'
import MonthSwitcher from '../components/MonthSwitcher'
import { useBudget } from '../hooks/useBudget'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'
import { suggestBudget } from '../services/budgetService'

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

// ── Auto-suggest modal ───────────────────────────────────────────────────────

function AutoSuggestModal({ poolAmount, onApply, onClose }) {
  const [allocation, setAllocation] = useState(String(Math.round(poolAmount || 0)))
  const [monthsBack, setMonthsBack] = useState(3)
  const [suggestions, setSuggestions] = useState(null)
  const [draftAmounts, setDraftAmounts] = useState({})
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState(null)

  const handleGenerate = async () => {
    const alloc = parseFloat(allocation)
    if (!alloc || alloc <= 0) { setError('Enter a valid allocation amount.'); return }
    setError(null)
    setLoading(true)
    try {
      const data = await suggestBudget(alloc, monthsBack)
      setSuggestions(data.suggestions)
      const drafts = {}
      for (const s of data.suggestions) drafts[s.id] = String(parseFloat(s.suggested_amount).toFixed(2))
      setDraftAmounts(drafts)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to generate suggestions.')
    } finally {
      setLoading(false)
    }
  }

  const totalDraft = suggestions
    ? suggestions.reduce((sum, s) => sum + (parseFloat(draftAmounts[s.id]) || 0), 0)
    : 0
  const diff = parseFloat(allocation || 0) - totalDraft

  const handleApply = async () => {
    if (!suggestions) return
    setApplying(true)
    try {
      await onApply(suggestions.map((s) => ({
        category_id: s.category_id,
        subcategory_id: s.subcategory_id,
        amount: parseFloat(draftAmounts[s.id]) || 0,
      })))
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to apply budgets.')
    } finally {
      setApplying(false)
    }
  }

  // Group suggestions by category for display
  const grouped = suggestions
    ? suggestions.reduce((acc, s) => {
        const key = s.category_id
        if (!acc[key]) acc[key] = { category_name: s.category_name, items: [] }
        acc[key].items.push(s)
        return acc
      }, {})
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-500" />
            <h2 className="font-semibold text-slate-800 text-base">AI Budget Suggestion</h2>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Config */}
        <div className="px-6 py-4 border-b border-slate-100 flex flex-wrap items-end gap-4">
          <div>
            <label className="label text-xs">Monthly allocation ($)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              className="input w-36 py-1.5 text-sm"
              value={allocation}
              onChange={(e) => setAllocation(e.target.value)}
            />
          </div>
          <div>
            <label className="label text-xs">Months of history</label>
            <select
              className="input py-1.5 text-sm"
              value={monthsBack}
              onChange={(e) => setMonthsBack(Number(e.target.value))}
            >
              {[1,2,3,4,5,6].map((n) => (
                <option key={n} value={n}>{n} month{n !== 1 ? 's' : ''}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="btn-primary py-1.5 text-sm flex items-center gap-1.5"
          >
            {loading ? <><Loader2 size={14} className="animate-spin" /> Generating…</> : <><Sparkles size={14} /> Generate</>}
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
            {error}
          </div>
        )}

        {/* Suggestions table */}
        {grouped && (
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">Subcategory</th>
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right pr-4">Avg/mo</th>
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">Suggested</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {Object.values(grouped).map((group) => (
                  <>
                    <tr key={group.category_name} className="bg-slate-50">
                      <td colSpan={3} className="py-1.5 px-1 text-xs font-semibold text-slate-600 uppercase tracking-wide">
                        {group.category_name}
                      </td>
                    </tr>
                    {group.items.map((s) => (
                      <tr key={s.id} className="hover:bg-slate-50">
                        <td className="py-2 pl-3 text-slate-700">
                          {s.subcategory_name || s.category_name}
                        </td>
                        <td className="py-2 pr-4 text-right text-slate-400 tabular-nums">
                          {formatCurrency(parseFloat(s.monthly_avg))}
                        </td>
                        <td className="py-2 text-right">
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            className="input w-24 py-0.5 text-sm text-right tabular-nums"
                            value={draftAmounts[s.id] ?? ''}
                            onChange={(e) => setDraftAmounts((prev) => ({ ...prev, [s.id]: e.target.value }))}
                          />
                        </td>
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        {grouped && (
          <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-between gap-4">
            <div className="text-sm">
              <span className="text-slate-600">Total: </span>
              <span className="font-semibold text-slate-800 tabular-nums">{formatCurrency(totalDraft)}</span>
              {Math.abs(diff) >= 0.01 && (
                <span className={`ml-3 text-xs font-medium ${diff > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {diff > 0 ? `${formatCurrency(diff)} under` : `${formatCurrency(Math.abs(diff))} over`} allocation
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={onClose} className="btn-secondary text-sm">Cancel</button>
              <button
                onClick={handleApply}
                disabled={applying}
                className="btn-primary text-sm flex items-center gap-1.5"
              >
                {applying ? <><Loader2 size={14} className="animate-spin" /> Applying…</> : <><Check size={14} /> Apply All</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
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
  const [suggestOpen, setSuggestOpen] = useState(false)

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

  const handleApplySuggestions = async (items) => {
    for (const item of items) {
      await saveBudget(item.category_id, item.subcategory_id, item.amount)
    }
  }

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

          <div className="flex gap-2 ml-auto">
            <button
              onClick={() => setSuggestOpen(true)}
              className="btn-secondary flex items-center gap-1.5"
            >
              <Sparkles size={14} className="text-indigo-500" /> Auto-suggest
            </button>
            <button
              onClick={handleFill}
              disabled={filling}
              className="btn-secondary"
            >
              {filling
                ? <><Loader2 size={14} className="animate-spin" /> Filling…</>
                : <><Copy size={14} /> Fill from Last Month</>}
            </button>
          </div>
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

      {suggestOpen && (
        <AutoSuggestModal
          poolAmount={poolInfo.pool_amount}
          onApply={handleApplySuggestions}
          onClose={() => setSuggestOpen(false)}
        />
      )}
    </div>
  )
}
