import { useState, useEffect } from 'react'
import TrendsLine from '../components/charts/TrendsLine'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import {
  getTrends, getTopMerchants, getYTD, getRecurring
} from '../services/reportService'
import { formatCurrency } from '../utils/currency'
import { formatDate, getMonthName } from '../utils/date'

const TABS = ['Spending Trends', 'Top Merchants', 'Year-to-Date', 'Recurring']

function TabButton({ label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 sm:px-4 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap ${
        active
          ? 'bg-indigo-600 text-white'
          : 'text-slate-600 hover:bg-slate-100'
      }`}
    >
      {label}
    </button>
  )
}

function SpendingTrends() {
  const { categories } = useCategories()
  const [categoryId, setCategoryId] = useState('')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTrends(12, categoryId || null)
      .then((res) => {
        if (cancelled) return
        const chartData = (Array.isArray(res) ? res : []).map((d) => ({
          ...d,
          label: `${getMonthName(d.month).slice(0, 3)} ${d.year}`,
        }))
        setData(chartData)
      })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [categoryId])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-slate-600">Category:</label>
        <select className="input max-w-xs" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All Categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      <div className="card">
        <h3 className="text-base font-semibold text-slate-700 mb-4">Spending Over Last 12 Months</h3>
        {loading ? <div className="h-64 skeleton rounded-lg" /> : <TrendsLine data={data} />}
      </div>
    </div>
  )
}

function TopMerchants() {
  const now = new Date()
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [year, setYear] = useState(now.getFullYear())
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTopMerchants(month, year, 10)
      .then((res) => { if (!cancelled) setData(Array.isArray(res) ? res : []) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [month, year])

  const months = Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: getMonthName(i + 1) }))
  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <select className="input max-w-[140px]" value={month} onChange={(e) => setMonth(Number(e.target.value))}>
          {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <select className="input max-w-[100px]" value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header">#</th>
              <th className="table-header">Merchant</th>
              <th className="table-header text-right">Total Spent</th>
              <th className="table-header text-right">Transactions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(4)].map((__, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded" /></td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-400">No data available.</td></tr>
            ) : (
              data.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50">
                  <td className="table-cell text-slate-400 font-medium">{i + 1}</td>
                  <td className="table-cell font-medium text-slate-800">{row.merchant_name || '—'}</td>
                  <td className="table-cell text-right tabular-nums font-medium">{formatCurrency(row.total_spent)}</td>
                  <td className="table-cell text-right tabular-nums text-slate-500">{row.transaction_count}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function YearToDate() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getYTD(year)
      .then((res) => { if (!cancelled) setData(Array.isArray(res) ? res : []) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [year])

  const months = Array.from({ length: 12 }, (_, i) => i + 1)
  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-slate-600">Year:</label>
        <select className="input max-w-[100px]" value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      {error && <div className="text-red-600 text-sm">{error}</div>}
      <div className="card p-0 overflow-x-auto">
        <table className="w-full text-sm whitespace-nowrap">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header sticky left-0 bg-slate-50 z-10">Category</th>
              {months.map((m) => (
                <th key={m} className="table-header text-right">{getMonthName(m).slice(0, 3)}</th>
              ))}
              <th className="table-header text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              [...Array(4)].map((_, i) => (
                <tr key={i}>
                  {[...Array(14)].map((__, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded w-16" /></td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr><td colSpan={14} className="px-4 py-8 text-center text-slate-400">No data for {year}.</td></tr>
            ) : (
              data.map((row) => {
                const total = (row.months ?? []).reduce((s, m) => s + (parseFloat(m.spent) || 0), 0)
                return (
                  <tr key={row.category_name} className="hover:bg-slate-50">
                    <td className="table-cell font-medium sticky left-0 bg-white hover:bg-slate-50">{row.category_name}</td>
                    {months.map((m) => {
                      const monthData = (row.months ?? []).find((md) => md.month === m)
                      const spent = parseFloat(monthData?.spent) || 0
                      const budget = parseFloat(monthData?.budget) || 0
                      const over = budget > 0 && spent > budget
                      return (
                        <td key={m} className={`table-cell text-right tabular-nums ${over ? 'text-red-600' : 'text-slate-700'}`}>
                          {spent > 0 ? formatCurrency(spent) : <span className="text-slate-300">—</span>}
                        </td>
                      )
                    })}
                    <td className="table-cell text-right tabular-nums font-semibold">{formatCurrency(total)}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RecurringList() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getRecurring()
      .then((res) => { if (!cancelled) setData(Array.isArray(res) ? res : []) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="space-y-4">
      {error && <div className="text-red-600 text-sm">{error}</div>}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header">Merchant</th>
              <th className="table-header text-right">Amount</th>
              <th className="table-header">Last Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              [...Array(4)].map((_, i) => (
                <tr key={i}>
                  {[...Array(3)].map((__, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 skeleton rounded" /></td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-400">No recurring transactions found.</td></tr>
            ) : (
              data.map((tx) => (
                <tr key={tx.id} className="hover:bg-slate-50">
                  <td className="table-cell font-medium text-slate-800">
                    {tx.merchant_name || tx.description || '—'}
                  </td>
                  <td className="table-cell text-right tabular-nums font-medium">
                    {formatCurrency(Math.abs(parseFloat(tx.amount) || 0))}
                  </td>
                  <td className="table-cell text-slate-500">
                    {formatDate(tx.transaction_date)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function Reports() {
  const [activeTab, setActiveTab] = useState(0)

  const tabContent = [
    <SpendingTrends key="trends" />,
    <TopMerchants key="merchants" />,
    <YearToDate key="ytd" />,
    <RecurringList key="recurring" />,
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Reports</h1>
        <p className="text-slate-500 text-sm mt-0.5">Spending analysis and insights</p>
      </div>

      <div className="overflow-x-auto pb-1 -mx-1 px-1">
        <div className="flex gap-1 p-1 bg-slate-100 rounded-lg w-fit min-w-full sm:min-w-0">
          {TABS.map((tab, i) => (
            <TabButton key={tab} label={tab} active={activeTab === i} onClick={() => setActiveTab(i)} />
          ))}
        </div>
      </div>

      {tabContent[activeTab]}
    </div>
  )
}
