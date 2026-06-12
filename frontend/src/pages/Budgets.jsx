import { useState } from 'react'
import {
  Check, ChevronDown, ChevronRight, Loader2, Lock, LockOpen,
  Pencil, Plus, Sparkles, Trash2, X,
} from 'lucide-react'
import MonthSwitcher from '../components/MonthSwitcher'
import { useBudget } from '../hooks/useBudget'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'
import { suggestBudget } from '../services/budgetService'

// ── Editable amount cell ────────────────────────────────────────────────────

function AmountCell({ value, onSave, disabled }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const [saving, setSaving] = useState(false)

  const commit = async () => {
    const amount = parseFloat(draft)
    if (!amount || amount <= 0) return
    setSaving(true)
    try {
      await onSave(amount)
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
          min="0.01"
          className="input w-28 py-1 text-sm"
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
      {!disabled && (
        <button
          onClick={() => { setDraft(value); setEditing(true) }}
          className="p-1 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
        >
          <Pencil size={14} />
        </button>
      )}
    </div>
  )
}

// ── Status badge (interim — progress bars land with the dashboard rework) ──

const STATUS_STYLES = {
  on_track: 'bg-emerald-50 text-emerald-700',
  approaching: 'bg-amber-50 text-amber-700',
  covered: 'bg-blue-50 text-blue-700',
  over: 'bg-red-50 text-red-700',
}

const STATUS_LABELS = {
  on_track: 'On track',
  approaching: 'Approaching',
  covered: 'Covered',
  over: 'Over',
}

function StatusBadge({ status }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLES[status] || ''}`}>
      {STATUS_LABELS[status] || status}
    </span>
  )
}

// ── Category group ──────────────────────────────────────────────────────────

function CategoryGroup({ group, isClosed, onSaveCap, onToggleLock, onRemove }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <>
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
              style={{ backgroundColor: group.category_color || '#94a3b8' }}
            />
            <span className="font-semibold text-slate-700">{group.category_name}</span>
          </div>
        </td>
        <td className="table-cell tabular-nums font-semibold text-slate-700">
          {formatCurrency(group.total_cap)}
        </td>
        <td className="table-cell tabular-nums text-slate-600">{formatCurrency(group.total_spent)}</td>
        <td className={`table-cell tabular-nums font-medium ${parseFloat(group.total_remaining) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
          {formatCurrency(group.total_remaining)}
        </td>
        <td className="table-cell tabular-nums text-slate-500">{formatCurrency(group.total_saved)}</td>
        <td className="table-cell" colSpan={2} />
      </tr>

      {expanded && group.subcategories.map((sub) => (
        <tr key={sub.subcategory_id} className="hover:bg-slate-50">
          <td className="table-cell pl-10 text-slate-600">{sub.subcategory_name}</td>
          <td className="table-cell">
            <AmountCell
              value={parseFloat(sub.cap) || 0}
              disabled={isClosed}
              onSave={(amount) => onSaveCap(sub.subcategory_id, amount)}
            />
          </td>
          <td className="table-cell tabular-nums text-slate-600">{formatCurrency(sub.spent)}</td>
          <td className={`table-cell tabular-nums ${parseFloat(sub.remaining) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
            {formatCurrency(sub.remaining)}
            {parseFloat(sub.covered_overage) > 0 && (
              <span className="ml-1.5 text-xs text-blue-600">
                ({formatCurrency(sub.covered_overage)} covered)
              </span>
            )}
          </td>
          <td className="table-cell tabular-nums text-slate-500">{formatCurrency(sub.saved_balance)}</td>
          <td className="table-cell"><StatusBadge status={sub.status} /></td>
          <td className="table-cell">
            <div className="flex items-center gap-1">
              <button
                title={sub.locked ? 'Unlock (AI may adjust)' : 'Lock (AI never adjusts)'}
                disabled={isClosed}
                onClick={() => onToggleLock(sub.subcategory_id, !sub.locked)}
                className={`p-1 rounded transition-colors ${sub.locked ? 'text-indigo-600 hover:bg-indigo-50' : 'text-slate-300 hover:text-slate-500 hover:bg-slate-100'}`}
              >
                {sub.locked ? <Lock size={14} /> : <LockOpen size={14} />}
              </button>
              <button
                title="Remove budget (deletes saved balance)"
                disabled={isClosed}
                onClick={() => onRemove(sub.subcategory_id, sub.subcategory_name, sub.saved_balance)}
                className="p-1 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </td>
        </tr>
      ))}
    </>
  )
}

// ── Unbudgeted picker ───────────────────────────────────────────────────────

function UnbudgetedSection({ unbudgeted, isClosed, onAdd }) {
  const [addingId, setAddingId] = useState(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  if (!unbudgeted?.length) return null

  // Group by category for display
  const grouped = unbudgeted.reduce((acc, s) => {
    if (!acc[s.category_id]) acc[s.category_id] = { name: s.category_name, items: [] }
    acc[s.category_id].items.push(s)
    return acc
  }, {})

  const commit = async (subcategoryId) => {
    const amount = parseFloat(draft)
    if (!amount || amount <= 0) return
    setSaving(true)
    try {
      await onAdd(subcategoryId, amount)
      setAddingId(null)
      setDraft('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-0 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-200">
        <h2 className="font-semibold text-slate-700">Not budgeted</h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Set a cap to start tracking a subcategory. Untracked subcategories are ignored by budgets.
        </p>
      </div>
      <div className="px-6 py-4 space-y-3">
        {Object.values(grouped).map((group) => (
          <div key={group.name}>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
              {group.name}
            </p>
            <div className="flex flex-wrap gap-2">
              {group.items.map((s) =>
                addingId === s.subcategory_id ? (
                  <span key={s.subcategory_id} className="inline-flex items-center gap-1 border border-indigo-200 bg-indigo-50 rounded-full pl-3 pr-1 py-0.5 text-sm">
                    {s.subcategory_name}
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="$"
                      className="input w-20 py-0.5 text-xs ml-1"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commit(s.subcategory_id)
                        if (e.key === 'Escape') { setAddingId(null); setDraft('') }
                      }}
                      autoFocus
                    />
                    <button
                      onClick={() => commit(s.subcategory_id)}
                      disabled={saving}
                      className="p-1 text-emerald-600 hover:bg-emerald-100 rounded-full"
                    >
                      <Check size={13} />
                    </button>
                  </span>
                ) : (
                  <button
                    key={s.subcategory_id}
                    disabled={isClosed}
                    onClick={() => { setAddingId(s.subcategory_id); setDraft('') }}
                    className="inline-flex items-center gap-1 border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 rounded-full px-3 py-0.5 text-sm text-slate-600 transition-colors disabled:opacity-50"
                  >
                    <Plus size={12} /> {s.subcategory_name}
                  </button>
                )
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Auto-suggest modal (legacy allocation flow — replaced in suggestions v2) ─

function AutoSuggestModal({ defaultAllocation, onApply, onClose }) {
  const [allocation, setAllocation] = useState(String(Math.round(defaultAllocation || 0)))
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
      // Only subcategory-level items apply under envelope budgeting (FR-1.3)
      const items = data.suggestions.filter((s) => s.subcategory_id)
      setSuggestions(items)
      const drafts = {}
      for (const s of items) drafts[s.id] = String(parseFloat(s.suggested_amount).toFixed(2))
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

  const handleApply = async () => {
    if (!suggestions) return
    setApplying(true)
    try {
      await onApply(suggestions
        .filter((s) => (parseFloat(draftAmounts[s.id]) || 0) > 0)
        .map((s) => ({
          subcategory_id: s.subcategory_id,
          amount: parseFloat(draftAmounts[s.id]),
        })))
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to apply budgets.')
    } finally {
      setApplying(false)
    }
  }

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
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-500" />
            <h2 className="font-semibold text-slate-800 text-base">AI Budget Suggestion</h2>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded transition-colors">
            <X size={18} />
          </button>
        </div>

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
                        <td className="py-2 pl-3 text-slate-700">{s.subcategory_name}</td>
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

        {grouped && (
          <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-between gap-4">
            <div className="text-sm">
              <span className="text-slate-600">Total: </span>
              <span className="font-semibold text-slate-800 tabular-nums">{formatCurrency(totalDraft)}</span>
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
    data,
    loading,
    error,
    saveCap,
    toggleLock,
    removeBudget,
    selectedMonth,
    selectedYear,
  } = useBudget()

  const [suggestOpen, setSuggestOpen] = useState(false)
  const [actionError, setActionError] = useState(null)

  const summary = data?.summary
  const isClosed = data?.is_closed ?? false

  const wrap = (fn) => async (...args) => {
    setActionError(null)
    try {
      await fn(...args)
    } catch (err) {
      setActionError(err.response?.data?.detail || err.message || 'Action failed')
    }
  }

  const handleRemove = wrap(async (subcategoryId, name, saved) => {
    const savedNum = parseFloat(saved) || 0
    const msg = savedNum > 0
      ? `Remove the budget for "${name}"? Its saved balance of ${formatCurrency(savedNum)} will be deleted (history is kept).`
      : `Remove the budget for "${name}"?`
    if (!window.confirm(msg)) return
    await removeBudget(subcategoryId)
  })

  const handleApplySuggestions = async (items) => {
    for (const item of items) {
      await saveCap(item.subcategory_id, item.amount)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Budgets</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Envelope caps per subcategory — surpluses roll into saved balances
          </p>
        </div>
        <MonthSwitcher month={selectedMonth} year={selectedYear} onChange={setMonth} />
      </div>

      {(error || actionError) && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error || actionError}
        </div>
      )}

      {isClosed && (
        <div className="p-3 bg-slate-100 border border-slate-200 rounded-lg text-slate-600 text-sm">
          This month is closed — caps and locks are read-only. Late transactions still update its actuals.
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div className="card flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          <span className="text-slate-600">
            Budgeted: <span className="font-semibold text-slate-800 tabular-nums">{formatCurrency(summary.total_budgeted)}</span>
          </span>
          <span className="text-slate-600">
            Spent: <span className="font-semibold text-slate-800 tabular-nums">{formatCurrency(summary.total_spent)}</span>
          </span>
          <span className="text-slate-600">
            Remaining:{' '}
            <span className={`font-semibold tabular-nums ${parseFloat(summary.total_remaining) < 0 ? 'text-red-600' : 'text-emerald-700'}`}>
              {formatCurrency(summary.total_remaining)}
            </span>
          </span>
          {parseFloat(summary.coverage_drawn) > 0 && (
            <span className="text-blue-600">
              Covered by savings: <span className="font-semibold tabular-nums">{formatCurrency(summary.coverage_drawn)}</span>
            </span>
          )}
          {summary.net_overage_count > 0 && (
            <span className="text-red-600 font-medium">
              {summary.net_overage_count} over budget
            </span>
          )}
          <div className="ml-auto">
            <button
              onClick={() => setSuggestOpen(true)}
              className="btn-secondary flex items-center gap-1.5"
              disabled={isClosed}
            >
              <Sparkles size={14} className="text-indigo-500" /> Auto-suggest
            </button>
          </div>
        </div>
      )}

      {/* Budgeted table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-700">Budgeted subcategories</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="table-header">Category / Subcategory</th>
                <th className="table-header">Cap</th>
                <th className="table-header">Spent</th>
                <th className="table-header">Remaining</th>
                <th className="table-header">Saved</th>
                <th className="table-header">Status</th>
                <th className="table-header w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                [...Array(6)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(7)].map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 skeleton rounded w-16" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : !data?.categories?.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No budgeted subcategories yet — pick some below to start.
                  </td>
                </tr>
              ) : (
                data.categories.map((group) => (
                  <CategoryGroup
                    key={group.category_id}
                    group={group}
                    isClosed={isClosed}
                    onSaveCap={wrap(saveCap)}
                    onToggleLock={wrap(toggleLock)}
                    onRemove={handleRemove}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Unbudgeted picker */}
      {!loading && (
        <UnbudgetedSection
          unbudgeted={data?.unbudgeted}
          isClosed={isClosed}
          onAdd={wrap(saveCap)}
        />
      )}

      {suggestOpen && (
        <AutoSuggestModal
          defaultAllocation={parseFloat(summary?.total_budgeted) || 0}
          onApply={handleApplySuggestions}
          onClose={() => setSuggestOpen(false)}
        />
      )}
    </div>
  )
}
