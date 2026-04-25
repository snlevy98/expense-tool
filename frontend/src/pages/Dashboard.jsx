import { useState, useEffect } from 'react'
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

export default function Dashboard() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const selectedYear = useAppStore((s) => s.selectedYear)
  const setMonth = useAppStore((s) => s.setMonth)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

      {/* Summary Cards */}
      {!loading && data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="card">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">Total Budget</p>
            <p className="text-2xl font-bold text-slate-800">{formatCurrency(data.total_budget)}</p>
          </div>
          <div className="card">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">Total Spent</p>
            <p className="text-2xl font-bold text-slate-800">{formatCurrency(data.total_spent)}</p>
          </div>
          <div className="card">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">Remaining</p>
            <p className={`text-2xl font-bold ${(data.total_budget - data.total_spent) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
              {formatCurrency(data.total_budget - data.total_spent)}
            </p>
          </div>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card space-y-2">
              <div className="h-3 skeleton rounded w-24" />
              <div className="h-8 skeleton rounded w-32" />
            </div>
          ))}
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
                    {(data?.rows ?? []).map((row) => (
                      <tr key={row.category_name} className="hover:bg-slate-50">
                        <td className="table-cell">
                          <div className="flex items-center gap-2">
                            <span
                              className="w-2.5 h-2.5 rounded-full shrink-0"
                              style={{ backgroundColor: row.category_color || '#94a3b8' }}
                            />
                            <span className="font-medium">{row.category_name}</span>
                          </div>
                        </td>
                        <td className="table-cell text-right tabular-nums">{formatCurrency(row.budget)}</td>
                        <td className="table-cell text-right tabular-nums font-medium">{formatCurrency(row.spent)}</td>
                        <td className={`table-cell text-right tabular-nums font-medium ${row.remaining < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                          {formatCurrency(row.remaining)}
                        </td>
                        <td className="table-cell">
                          <BudgetStatusBadge status={row.status} />
                        </td>
                      </tr>
                    ))}
                    {/* Totals row */}
                    {data && (
                      <tr className="bg-slate-50 font-semibold border-t border-slate-200">
                        <td className="table-cell text-slate-700">Total</td>
                        <td className="table-cell text-right tabular-nums">{formatCurrency(data.total_budget)}</td>
                        <td className="table-cell text-right tabular-nums">{formatCurrency(data.total_spent)}</td>
                        <td className={`table-cell text-right tabular-nums ${(data.total_budget - data.total_spent) < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                          {formatCurrency(data.total_budget - data.total_spent)}
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
    </div>
  )
}
