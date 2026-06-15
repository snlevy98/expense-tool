import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Check, ChevronDown, ChevronRight, Copy, Loader2, Lock, LockOpen,
  Pencil, PiggyBank, Plus, Sparkles, Trash2, X,
} from 'lucide-react'
import MonthSwitcher from '../components/MonthSwitcher'
import { useBudget } from '../hooks/useBudget'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'
import { getMonthName } from '../utils/date'
import { suggestBudget, applySuggestions, copyBudgets } from '../services/budgetService'

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

// ── Subcategory progress bar (four envelope states) ─────────────────────────

const BAR_FILL = {
  on_track: 'bg-emerald-500',
  approaching: 'bg-amber-500',
  over: 'bg-red-500',
}

// "Covered" overage is drawn from savings — a blue diagonal stripe signals it
// differs from ordinary spend-within-cap.
const COVERED_STRIPES = {
  backgroundImage:
    'repeating-linear-gradient(45deg, #3b82f6 0, #3b82f6 4px, #60a5fa 4px, #60a5fa 8px)',
}

const LABEL_COLOR = {
  on_track: 'text-slate-400',
  approaching: 'text-amber-600',
  covered: 'text-blue-600',
  over: 'text-red-600',
}

function ProgressBar({ row }) {
  const cap = parseFloat(row.cap) || 0
  const spent = parseFloat(row.spent) || 0
  const pct = cap > 0 ? (spent / cap) * 100 : spent > 0 ? 100 : 0
  const width = Math.max(0, Math.min(100, pct))
  const covered = parseFloat(row.covered_overage) || 0
  const netOver = parseFloat(row.net_overage) || 0

  let label
  if (row.status === 'over') label = `${formatCurrency(netOver)} over`
  else if (row.status === 'covered') label = `${formatCurrency(covered)} covered`
  else label = `${Math.round(pct)}%`

  return (
    <div className="w-full" title={`${formatCurrency(spent)} of ${formatCurrency(cap)}`}>
      <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${row.status === 'covered' ? '' : BAR_FILL[row.status] || 'bg-slate-300'}`}
          style={{ width: `${width}%`, ...(row.status === 'covered' ? COVERED_STRIPES : {}) }}
        />
      </div>
      <span className={`mt-0.5 block text-[11px] tabular-nums ${LABEL_COLOR[row.status] || 'text-slate-400'}`}>
        {label}
      </span>
    </div>
  )
}

// ── Saved-balance chip ───────────────────────────────────────────────────────

function SavedChip({ value }) {
  const v = parseFloat(value) || 0
  if (v <= 0) return <span className="text-slate-300">—</span>
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 tabular-nums">
      <PiggyBank size={12} />
      {formatCurrency(v)}
    </span>
  )
}

// ── Category group ──────────────────────────────────────────────────────────

function CategoryGroup({ group, isClosed, onSaveCap, onToggleLock, onRemove, onDrill }) {
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
          <td className="table-cell pl-10">
            <button
              onClick={() => onDrill(group.category_id, sub.subcategory_id)}
              className="text-left text-slate-600 hover:text-indigo-600 hover:underline transition-colors"
              title="View this subcategory's transactions for this month"
            >
              {sub.subcategory_name}
            </button>
          </td>
          <td className="table-cell">
            <AmountCell
              value={parseFloat(sub.cap) || 0}
              onSave={(amount) => onSaveCap(sub.subcategory_id, amount)}
            />
          </td>
          <td className="table-cell tabular-nums text-slate-600">{formatCurrency(sub.spent)}</td>
          <td className={`table-cell tabular-nums ${parseFloat(sub.remaining) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
            {formatCurrency(sub.remaining)}
          </td>
          <td className="table-cell"><SavedChip value={sub.saved_balance} /></td>
          <td className="table-cell"><ProgressBar row={sub} /></td>
          <td className="table-cell">
            <div className="flex items-center gap-1">
              <button
                title={sub.locked ? 'Unlock (AI may adjust)' : 'Lock (AI never adjusts)'}
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

function UnbudgetedSection({ unbudgeted, onAdd }) {
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

// ── Copy-from-another-month modal ────────────────────────────────────────────

function CopyFromModal({ targetMonth, targetYear, onClose, onCopied }) {
  const prevM = targetMonth - 1 < 1 ? 12 : targetMonth - 1
  const prevY = targetMonth - 1 < 1 ? targetYear - 1 : targetYear
  const [fromMonth, setFromMonth] = useState(prevM)
  const [fromYear, setFromYear] = useState(prevY)
  const [overwrite, setOverwrite] = useState(true)
  const [copying, setCopying] = useState(false)
  const [error, setError] = useState(null)

  const months = Array.from({ length: 12 }, (_, i) => i + 1)
  const years = Array.from({ length: 5 }, (_, i) => targetYear + 1 - i)
  const sameAsTarget = fromMonth === targetMonth && fromYear === targetYear

  const handleCopy = async () => {
    if (sameAsTarget) { setError('Pick a different month to copy from.'); return }
    setError(null)
    setCopying(true)
    try {
      await copyBudgets({ fromMonth, fromYear, toMonth: targetMonth, toYear: targetYear, overwrite })
      await onCopied?.()
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to copy budget.')
    } finally {
      setCopying(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Copy size={18} className="text-slate-500" />
            <h2 className="font-semibold text-slate-800 text-base">Copy budget from another month</h2>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <p className="text-sm text-slate-500">
            Copy caps into <span className="font-medium text-slate-700">{getMonthName(targetMonth)} {targetYear}</span> from:
          </p>
          <div className="flex gap-2">
            <select className="input" value={fromMonth} onChange={(e) => setFromMonth(Number(e.target.value))}>
              {months.map((m) => <option key={m} value={m}>{getMonthName(m)}</option>)}
            </select>
            <select className="input max-w-[110px]" value={fromYear} onChange={(e) => setFromYear(Number(e.target.value))}>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="w-3.5 h-3.5 rounded accent-indigo-600"
            />
            Overwrite caps that already exist this month
          </label>
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">{error}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary text-sm">Cancel</button>
          <button
            onClick={handleCopy}
            disabled={copying || sameAsTarget}
            className="btn-primary text-sm flex items-center gap-1.5"
          >
            {copying ? <><Loader2 size={14} className="animate-spin" /> Copying…</> : <><Copy size={14} /> Copy</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── AI suggestion review modal (v2 — history-driven, no allocation) ──────────

function AutoSuggestModal({ month, year, onClose, onApplied }) {
  const [data, setData] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [selected, setSelected] = useState(() => new Set())
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const resp = await suggestBudget(month, year)
        if (cancelled) return
        const d = {}
        const sel = new Set()
        for (const s of resp.suggestions) {
          d[s.subcategory_id] = String(parseFloat(s.suggested_amount))
          if (!s.locked) sel.add(s.subcategory_id)
        }
        setData(resp)
        setDrafts(d)
        setSelected(sel)
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.detail || err.message || 'Failed to generate suggestions.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [month, year])

  const toggleSelected = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const income = parseFloat(data?.last_month_income) || 0

  // Projected total = locked caps + selected (edited) suggestions + unselected
  // rows left at their current cap.
  const projected = (data?.suggestions ?? []).reduce((sum, s) => {
    if (s.locked) return sum + (parseFloat(s.current_cap) || 0)
    if (selected.has(s.subcategory_id)) return sum + (parseFloat(drafts[s.subcategory_id]) || 0)
    return sum + (parseFloat(s.current_cap) || 0)
  }, 0)
  const overIncome = income > 0 && projected > income

  const handleApply = async () => {
    const items = (data?.suggestions ?? [])
      .filter((s) => !s.locked && selected.has(s.subcategory_id) && (parseFloat(drafts[s.subcategory_id]) || 0) > 0)
      .map((s) => ({ subcategory_id: s.subcategory_id, amount: parseFloat(drafts[s.subcategory_id]) }))
    if (items.length === 0) { onClose(); return }
    setApplying(true)
    setError(null)
    try {
      await applySuggestions(month, year, items)
      await onApplied?.()
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to apply budgets.')
    } finally {
      setApplying(false)
    }
  }

  const grouped = (data?.suggestions ?? []).reduce((acc, s) => {
    if (!acc[s.category_id]) acc[s.category_id] = { category_name: s.category_name, items: [] }
    acc[s.category_id].items.push(s)
    return acc
  }, {})

  const selectedCount = (data?.suggestions ?? []).filter(
    (s) => !s.locked && selected.has(s.subcategory_id)
  ).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-500" />
            <h2 className="font-semibold text-slate-800 text-base">Suggested Budget</h2>
            {data && (
              <span className={`text-xs px-2 py-0.5 rounded-full ${data.source === 'ai' ? 'bg-indigo-50 text-indigo-600' : 'bg-slate-100 text-slate-500'}`}>
                {data.source === 'ai' ? `AI · ${data.provider}` : 'Estimated (non-AI)'}
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600 rounded transition-colors">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-16 text-slate-400 text-sm gap-2">
            <Loader2 size={16} className="animate-spin" /> Analyzing {data?.months_analyzed ?? 'recent'} months of history…
          </div>
        ) : (data?.suggestions ?? []).length === 0 ? (
          <div className="flex-1 flex items-center justify-center py-16 text-slate-400 text-sm">
            Not enough history to suggest a budget yet.
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left">
                  <th className="pb-2 w-8" />
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide">Subcategory</th>
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right pr-3">Avg · Max</th>
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right pr-3">Current</th>
                  <th className="pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wide text-right">Suggested</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {Object.values(grouped).map((group) => (
                  <>
                    <tr key={group.category_name} className="bg-slate-50">
                      <td colSpan={5} className="py-1.5 px-1 text-xs font-semibold text-slate-600 uppercase tracking-wide">
                        {group.category_name}
                      </td>
                    </tr>
                    {group.items.map((s) => {
                      const isSel = selected.has(s.subcategory_id)
                      return (
                        <tr key={s.subcategory_id} className={`hover:bg-slate-50 ${s.locked ? 'opacity-70' : ''}`}>
                          <td className="py-2 pl-1">
                            <input
                              type="checkbox"
                              className="w-3.5 h-3.5 rounded accent-indigo-600"
                              checked={!s.locked && isSel}
                              disabled={s.locked}
                              onChange={() => toggleSelected(s.subcategory_id)}
                            />
                          </td>
                          <td className="py-2 text-slate-700">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {s.subcategory_name}
                              {s.locked && (
                                <span className="inline-flex items-center gap-0.5 text-[11px] text-indigo-600">
                                  <Lock size={11} /> locked
                                </span>
                              )}
                              {s.is_unbudgeted_candidate && (
                                <span className="text-[11px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">New</span>
                              )}
                            </div>
                            {s.rationale && (
                              <p className="text-[11px] text-slate-400 mt-0.5">{s.rationale}</p>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-right text-slate-400 tabular-nums whitespace-nowrap">
                            {formatCurrency(parseFloat(s.monthly_avg))} · {formatCurrency(parseFloat(s.historical_max))}
                          </td>
                          <td className="py-2 pr-3 text-right text-slate-500 tabular-nums">
                            {parseFloat(s.current_cap) > 0 ? formatCurrency(parseFloat(s.current_cap)) : '—'}
                          </td>
                          <td className="py-2 text-right">
                            {s.locked ? (
                              <span className="tabular-nums text-slate-500 pr-1">{formatCurrency(parseFloat(s.current_cap))}</span>
                            ) : (
                              <input
                                type="number"
                                min="0"
                                step="5"
                                className="input w-24 py-0.5 text-sm text-right tabular-nums"
                                value={drafts[s.subcategory_id] ?? ''}
                                onChange={(e) => setDrafts((prev) => ({ ...prev, [s.subcategory_id]: e.target.value }))}
                              />
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && (data?.suggestions ?? []).length > 0 && (
          <div className="px-6 py-4 border-t border-slate-200 flex items-center justify-between gap-4 flex-wrap">
            <div className="text-sm space-y-0.5">
              <div>
                <span className="text-slate-600">Projected total: </span>
                <span className={`font-semibold tabular-nums ${overIncome ? 'text-red-600' : 'text-slate-800'}`}>
                  {formatCurrency(projected)}
                </span>
              </div>
              {income > 0 && (
                <div className={`text-xs ${overIncome ? 'text-red-600' : 'text-emerald-600'}`}>
                  {overIncome
                    ? `${formatCurrency(projected - income)} over last month's income (${formatCurrency(income)})`
                    : `Within last month's income (${formatCurrency(income)})`}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={onClose} className="btn-secondary text-sm">Cancel</button>
              <button
                onClick={handleApply}
                disabled={applying || selectedCount === 0}
                className="btn-primary text-sm flex items-center gap-1.5"
              >
                {applying ? <><Loader2 size={14} className="animate-spin" /> Applying…</> : <><Check size={14} /> Apply {selectedCount} selected</>}
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
  const navigate = useNavigate()
  const setMonth = useAppStore((s) => s.setMonth)
  const {
    data,
    loading,
    error,
    saveCap,
    toggleLock,
    removeBudget,
    refetch,
    selectedMonth,
    selectedYear,
  } = useBudget()

  const [suggestOpen, setSuggestOpen] = useState(false)
  const [copyOpen, setCopyOpen] = useState(false)
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

  // Drill-down: open the Transactions page pre-filtered to this subcategory for
  // the selected month (date_to is inclusive on the backend).
  const handleDrill = (categoryId, subcategoryId) => {
    const mm = String(selectedMonth).padStart(2, '0')
    const lastDay = new Date(selectedYear, selectedMonth, 0).getDate()
    const params = new URLSearchParams({
      category_id: categoryId,
      subcategory_id: subcategoryId,
      date_from: `${selectedYear}-${mm}-01`,
      date_to: `${selectedYear}-${mm}-${String(lastDay).padStart(2, '0')}`,
    })
    navigate(`/transactions?${params.toString()}`)
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
          This month is closed. You can still edit its caps for an accurate record, but changes here don't affect saved balances or any other month. Budgets can't be removed once closed.
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
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setCopyOpen(true)}
              className="btn-secondary flex items-center gap-1.5"
            >
              <Copy size={14} className="text-slate-500" /> Copy from…
            </button>
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
                <th className="table-header w-44">Progress</th>
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
                    onDrill={handleDrill}
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
          onAdd={wrap(saveCap)}
        />
      )}

      {suggestOpen && (
        <AutoSuggestModal
          month={selectedMonth}
          year={selectedYear}
          onClose={() => setSuggestOpen(false)}
          onApplied={refetch}
        />
      )}

      {copyOpen && (
        <CopyFromModal
          targetMonth={selectedMonth}
          targetYear={selectedYear}
          onClose={() => setCopyOpen(false)}
          onCopied={refetch}
        />
      )}
    </div>
  )
}
