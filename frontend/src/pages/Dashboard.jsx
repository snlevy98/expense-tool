import { useState, useEffect, Fragment } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useAppStore } from '../store/appStore'
import MonthSwitcher from '../components/MonthSwitcher'
import BudgetStatusBadge from '../components/BudgetStatusBadge'
import SpendingDonut from '../components/charts/SpendingDonut'
import { getDashboard } from '../services/reportService'
import { formatCurrency } from '../utils/currency'

function SkeletonRow() {
  return (
    <tr>
      {[...Array(5)].map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 skeleton rounded" style={{ width: `${50 + (i * 17) % 40}%` }} />
        </td>
      ))}
    </tr>
  )
}

function SummaryField({ label, value, highlight }) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-4 py-3 min-w-0">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wider whitespace-nowrap">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${highlight ?? 'text-slate-800'}`}>
        {value}
      </p>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const selectedYear = useAppStore((s) => s.selectedYear)
  const setMonth = useAppStore((s) => s.setMonth)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedCategories, setExpandedCategories] = useState(new Set())

  const toggleCategory = (categoryId) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(categoryId)) next.delete(categoryId)
      else next.add(categoryId)
      return next
    })
  }

  const drillToTransactions = (categoryId, subcategoryId) => {
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

  useEffect(() => {
    let cancelled = false
    const fetch = async () => {
      setLoading(true)
      setError(null)
      try {
        const result = await getDashboard(selectedMonth, selectedYear)
        if (!cancelled) setData(result)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load dashboard')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch()
    return () => { cancelled = true }
  }, [selectedMonth, selectedYear])

  const summary = data?.summary ?? null

  const donutData = (data?.rows ?? []).map((row) => ({
    name: row.category_name,
    value: parseFloat(row.spent) || 0,
    color: row.category_color || '#6366f1',
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Dashboard</h1>
          <p className="text-slate-500 text-sm mt-0.5">Monthly budget overview</p>
        </div>
        <MonthSwitcher month={selectedMonth} year={selectedYear} onChange={setMonth} />
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      {/* 6-field Summary Row */}
      {loading ? (
        <div className="card flex flex-wrap divide-x divide-slate-100">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="flex flex-col items-center gap-1 px-4 py-3 flex-1 min-w-[120px]">
              <div className="h-3 skeleton rounded w-16" />
              <div className="h-6 skeleton rounded w-24" />
            </div>
          ))}
        </div>
      ) : summary && (
        <div className="card p-0 overflow-hidden">
          <div className="flex flex-wrap divide-y sm:divide-y-0 sm:divide-x divide-slate-100">
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Income"
                value={formatCurrency(summary.income)}
                highlight="text-emerald-700"
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Budget"
                value={formatCurrency(summary.budget)}
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Spent"
                value={formatCurrency(summary.spent)}
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Remaining"
                value={formatCurrency(summary.remaining)}
                highlight={parseFloat(summary.remaining) < 0 ? 'text-red-600' : 'text-emerald-700'}
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Investments"
                value={formatCurrency(summary.investments)}
                highlight="text-indigo-700"
              />
            </div>
            <div className="flex-1 min-w-[120px]">
              <SummaryField
                label="Savings"
                value={formatCurrency(summary.savings)}
                highlight={parseFloat(summary.savings) < 0 ? 'text-red-600' : 'text-emerald-700'}
              />
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Donut Chart */}
        <div className="card lg:col-span-2">
          <h2 className="text-base font-semibold text-slate-700 mb-4">Spending Breakdown</h2>
          {loading ? (
            <div className="h-64 skeleton rounded-lg" />
          ) : (
            <SpendingDonut data={donutData} />
          )}
        </div>

        {/* Category Table */}
        <div className="card lg:col-span-3 p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-700">Budget by Category</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="table-header">Category</th>
                  <th className="table-header text-right">Budget</th>
                  <th className="table-header text-right">Spent</th>
                  <th className="table-header text-right">Remaining</th>
                  <th className="table-header">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  [...Array(5)].map((_, i) => <SkeletonRow key={i} />)
                ) : (data?.rows ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400">No data for this month.</td>
                  </tr>
                ) : (
                  <>
                    {(data?.rows ?? []).map((row) => {
                      const hasSubs = (row.subcategories ?? []).length > 0
                      const isExpanded = expandedCategories.has(row.category_id)
                      return (
                        <>
                          <tr
                            key={row.category_id}
                            className={`${hasSubs ? 'cursor-pointer' : ''} hover:bg-slate-50`}
                            onClick={() => hasSubs && toggleCategory(row.category_id)}
                          >
                            <td className="table-cell">
                              <div className="flex items-center gap-2">
                                {hasSubs ? (
                                  isExpanded
                                    ? <ChevronDown size={14} className="text-slate-400 shrink-0" />
                                    : <ChevronRight size={14} className="text-slate-400 shrink-0" />
                                ) : (
                                  <span className="w-3.5 shrink-0" />
                                )}
                                <span
                                  className="w-2.5 h-2.5 rounded-full shrink-0"
                                  style={{ backgroundColor: row.category_color || '#94a3b8' }}
                                />
                                <span className="font-medium">{row.category_name}</span>
                              </div>
                            </td>
                            <td className="table-cell text-right tabular-nums">{formatCurrency(row.budget)}</td>
                            <td className="table-cell text-right tabular-nums font-medium">{formatCurrency(row.spent)}</td>
                            <td className={`table-cell text-right tabular-nums font-medium ${parseFloat(row.remaining) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                              {formatCurrency(row.remaining)}
                            </td>
                            <td className="table-cell">
                              <BudgetStatusBadge status={row.status} />
                            </td>
                          </tr>

                          {/* Subcategory rows */}
                          {isExpanded && (row.subcategories ?? []).map((sub) => (
                            <tr key={sub.subcategory_id} className="bg-slate-50/60">
                              <td className="table-cell">
                                <div className="flex items-center gap-2 pl-8">
                                  <span className="w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" />
                                  <span className="text-slate-600">{sub.subcategory_name}</span>
                                </div>
                              </td>
                              <td className="table-cell text-right tabular-nums text-slate-500">{formatCurrency(sub.budget)}</td>
                              <td className="table-cell text-right tabular-nums font-medium text-slate-700">{formatCurrency(sub.spent)}</td>
                              <td className={`table-cell text-right tabular-nums font-medium ${parseFloat(sub.remaining) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                                {formatCurrency(sub.remaining)}
                              </td>
                              <td className="table-cell">
                                <BudgetStatusBadge status={sub.status} />
                              </td>
                            </tr>
                          ))}
                        </>
                      )
                    })}
                    {/* Totals row */}
                    {data && (
                      <tr className="bg-slate-50 font-semibold border-t border-slate-200">
                        <td className="table-cell text-slate-700 pl-9">Total</td>
                        <td className="table-cell text-right tabular-nums">{formatCurrency(data.total_budget)}</td>
                        <td className="table-cell text-right tabular-nums">{formatCurrency(data.total_spent)}</td>
                        <td className={`table-cell text-right tabular-nums ${(parseFloat(data.total_budget) - parseFloat(data.total_spent)) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                          {formatCurrency(parseFloat(data.total_budget) - parseFloat(data.total_spent))}
                        </td>
                        <td className="table-cell" />
                      </tr>
                    )}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* System categories (excluded from budgeting) */}
      {!loading && (data?.system_categories?.length > 0) && (
        <div className="card p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-700">System Categories</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Activity this month in categories excluded from budgeting
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="table-header">Category</th>
                  <th className="table-header text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.system_categories.map((cat) => (
                  <Fragment key={cat.category_id}>
                    <tr className="bg-slate-50/60">
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-full shrink-0"
                            style={{ backgroundColor: cat.category_color || '#94a3b8' }}
                          />
                          <span className="font-semibold text-slate-700">{cat.category_name}</span>
                        </div>
                      </td>
                      <td className={`table-cell text-right tabular-nums font-semibold ${parseFloat(cat.amount) < 0 ? 'text-emerald-600' : 'text-slate-700'}`}>
                        {formatCurrency(cat.amount)}
                      </td>
                    </tr>
                    {cat.subcategories.map((sub) => (
                      <tr key={sub.subcategory_id} className="hover:bg-slate-50">
                        <td className="table-cell">
                          <button
                            onClick={() => drillToTransactions(cat.category_id, sub.subcategory_id)}
                            className="text-left text-slate-600 hover:text-indigo-600 hover:underline transition-colors pl-6"
                            title="View this subcategory's transactions for this month"
                          >
                            {sub.subcategory_name}
                          </button>
                        </td>
                        <td className={`table-cell text-right tabular-nums ${parseFloat(sub.amount) < 0 ? 'text-emerald-600' : 'text-slate-600'}`}>
                          {formatCurrency(sub.amount)}
                        </td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
