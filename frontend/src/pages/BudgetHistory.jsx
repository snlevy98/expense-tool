import { useState, useEffect, useMemo } from 'react'
import BudgetHistoryChart from '../components/charts/BudgetHistoryChart'
import { useCategories } from '../hooks/useCategories'
import { getBudgetHistory } from '../services/budgetService'
import { formatCurrency } from '../utils/currency'

const RANGES = [
  { value: 3, label: 'Last 3 months' },
  { value: 6, label: 'Last 6 months' },
  { value: 12, label: 'Last 12 months' },
]

function ymString(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`
}

// Trailing `months` window ending at the current month.
function rangeFor(months) {
  const now = new Date()
  const toY = now.getFullYear()
  const toM = now.getMonth() + 1
  let fM = toM
  let fY = toY
  for (let i = 0; i < months - 1; i++) {
    fM -= 1
    if (fM < 1) { fM = 12; fY -= 1 }
  }
  return { from: ymString(fY, fM), to: ymString(toY, toM) }
}

export default function BudgetHistory() {
  const { categories, getSubcategories } = useCategories()
  const [monthsBack, setMonthsBack] = useState(6)
  const [categoryId, setCategoryId] = useState('')
  const [subcategoryId, setSubcategoryId] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const subcategories = getSubcategories(categoryId)
  const { from, to } = useMemo(() => rangeFor(monthsBack), [monthsBack])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getBudgetHistory({ from, to, categoryId: categoryId || null, subcategoryId: subcategoryId || null })
      .then((res) => { if (!cancelled) setData(res) })
      .catch((err) => { if (!cancelled) setError(err.response?.data?.detail || err.message || 'Failed to load history') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [from, to, categoryId, subcategoryId])

  const points = data?.points ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Budget History</h1>
        <p className="text-slate-500 text-sm mt-0.5">Budget vs. actual and saved-balance trend over time</p>
      </div>

      {/* Controls */}
      <div className="card flex flex-wrap items-center gap-3">
        <select
          className="input max-w-[160px]"
          value={monthsBack}
          onChange={(e) => setMonthsBack(Number(e.target.value))}
        >
          {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <select
          className="input max-w-[200px]"
          value={categoryId}
          onChange={(e) => { setCategoryId(e.target.value); setSubcategoryId('') }}
        >
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select
          className="input max-w-[200px]"
          value={subcategoryId}
          onChange={(e) => setSubcategoryId(e.target.value)}
          disabled={!categoryId || subcategories.length === 0}
        >
          <option value="">All subcategories</option>
          {subcategories.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      {/* Chart */}
      <div className="card">
        <h2 className="text-base font-semibold text-slate-700 mb-4">Budget vs. Actual</h2>
        {loading ? <div className="h-72 skeleton rounded-lg" /> : <BudgetHistoryChart points={points} />}
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-700">Monthly detail</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="table-header">Month</th>
                <th className="table-header text-right">Budget</th>
                <th className="table-header text-right">Spent</th>
                <th className="table-header text-right">Surplus</th>
                <th className="table-header text-right">Over</th>
                <th className="table-header text-right">Saved</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                [...Array(6)].map((_, i) => (
                  <tr key={i}>
                    {[...Array(6)].map((__, j) => (
                      <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded w-16" /></td>
                    ))}
                  </tr>
                ))
              ) : points.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">No history in this range.</td></tr>
              ) : (
                points.map((p) => {
                  const surplus = parseFloat(p.surplus) || 0
                  const overage = parseFloat(p.overage) || 0
                  const covered = parseFloat(p.covered_overage) || 0
                  const net = parseFloat(p.net_overage) || 0
                  return (
                    <tr key={p.label} className="hover:bg-slate-50">
                      <td className="table-cell font-medium text-slate-700">{p.label}</td>
                      <td className="table-cell text-right tabular-nums">{formatCurrency(p.budget)}</td>
                      <td className="table-cell text-right tabular-nums font-medium">{formatCurrency(p.spent)}</td>
                      <td className="table-cell text-right tabular-nums text-emerald-600">
                        {surplus > 0 ? formatCurrency(surplus) : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="table-cell text-right tabular-nums">
                        {overage > 0 ? (
                          <span>
                            <span className={net > 0 ? 'text-red-600 font-medium' : 'text-slate-500'}>
                              {formatCurrency(overage)}
                            </span>
                            {covered > 0 && (
                              <span className="block text-[11px] text-blue-600">{formatCurrency(covered)} covered</span>
                            )}
                          </span>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="table-cell text-right tabular-nums text-slate-600">{formatCurrency(p.saved_balance)}</td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
