import { useState, useRef, useCallback } from 'react'
import {
  ShoppingCart,
  Upload,
  CheckCircle,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Leaf,
  Package,
} from 'lucide-react'
import { api } from '../services/api'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { formatCurrency } from '../utils/currency'
import { formatDate } from '../utils/date'

// ─── Small helpers ────────────────────────────────────────────────────────────

function FileDropZone({ label, file, onChange, accept = '.csv' }) {
  const ref = useRef()
  return (
    <div>
      <p className="text-sm font-medium text-slate-600 mb-1">{label}</p>
      <div
        className="border-2 border-dashed border-slate-300 rounded-lg px-4 py-5 text-center
                   hover:border-indigo-400 transition-colors cursor-pointer"
        onClick={() => ref.current?.click()}
      >
        {file ? (
          <p className="text-sm font-medium text-slate-700">
            {file.name}{' '}
            <span className="text-slate-400 font-normal">
              ({(file.size / 1024).toFixed(1)} KB)
            </span>
          </p>
        ) : (
          <p className="text-sm text-slate-500">Click to choose a CSV file</p>
        )}
        <input ref={ref} type="file" accept={accept} className="hidden" onChange={(e) => onChange(e.target.files[0] || null)} />
      </div>
    </div>
  )
}

function CategorySelect({ categories, value, onChange, disabled }) {
  return (
    <select
      className="input py-1 text-sm min-w-[160px]"
      value={value || ''}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled}
    >
      <option value="">— Category —</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  )
}

function SubcategorySelect({ categories, categoryId, value, onChange, disabled }) {
  const subs = categories.find((c) => c.id === categoryId)?.subcategories ?? []
  return (
    <select
      className="input py-1 text-sm min-w-[150px]"
      value={value || ''}
      onChange={(e) => onChange(e.target.value || null)}
      disabled={disabled || !categoryId || subs.length === 0}
    >
      <option value="">— Subcategory —</option>
      {subs.map((s) => (
        <option key={s.id} value={s.id}>{s.name}</option>
      ))}
    </select>
  )
}

// ─── Grocery section ──────────────────────────────────────────────────────────

function GrocerySection({ matches, categories, onApply }) {
  const defaultGroceryCat = categories.find((c) =>
    /grocer/i.test(c.name)
  )?.id ?? ''

  const [groceryCatId, setGroceryCatId] = useState(defaultGroceryCat)
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState(false)

  const matched = matches.filter((m) => m.transaction_id)
  const unmatched = matches.filter((m) => !m.transaction_id)

  const handleApply = async () => {
    setApplying(true)
    try {
      await onApply(
        matched.map((m) => ({
          transaction_id: m.transaction_id,
          order_id: m.order_id,
          category_id: groceryCatId || null,
        }))
      )
      setDone(true)
    } finally {
      setApplying(false)
    }
  }

  if (done) {
    return (
      <div className="card flex items-center gap-3 text-emerald-700 bg-emerald-50 border border-emerald-200">
        <CheckCircle size={18} />
        <span className="text-sm font-medium">
          {matched.length} grocery order{matched.length !== 1 ? 's' : ''} updated as Whole Foods Market
        </span>
      </div>
    )
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center gap-2">
        <Leaf size={18} className="text-emerald-600" />
        <h3 className="font-semibold text-slate-800">
          Grocery Orders — {matched.length} matched
          {unmatched.length > 0 && (
            <span className="ml-2 text-amber-600 text-sm font-normal">
              ({unmatched.length} no match found)
            </span>
          )}
        </h3>
      </div>
      <p className="text-sm text-slate-500">
        These will be updated to <strong>Whole Foods Market - Uptown Dallas</strong> with the category below.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left">
              <th className="table-header">Order Date</th>
              <th className="table-header">Items</th>
              <th className="table-header">Amount</th>
              <th className="table-header">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {matches.map((m) => (
              <tr key={m.order_id} className={!m.transaction_id ? 'opacity-50' : ''}>
                <td className="table-cell text-slate-500 whitespace-nowrap">{m.order_date}</td>
                <td className="table-cell text-slate-700 max-w-sm">
                  <span className="line-clamp-2">{m.items_summary}</span>
                </td>
                <td className="table-cell font-semibold tabular-nums whitespace-nowrap">
                  {formatCurrency(m.amount)}
                </td>
                <td className="table-cell whitespace-nowrap">
                  {m.transaction_id ? (
                    <span className="text-emerald-600 text-xs font-medium">✓ matched</span>
                  ) : (
                    <span className="text-amber-600 text-xs font-medium">⚠ no transaction found</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {matched.length > 0 && (
        <div className="flex items-center gap-3 pt-2 border-t border-slate-100">
          <span className="text-sm text-slate-600">Category:</span>
          <CategorySelect
            categories={categories}
            value={groceryCatId}
            onChange={setGroceryCatId}
            disabled={applying}
          />
          <button
            onClick={handleApply}
            disabled={applying || !groceryCatId}
            className="btn-primary ml-auto"
          >
            {applying ? (
              <><Loader2 size={15} className="animate-spin mr-1.5" /> Applying…</>
            ) : (
              `Apply ${matched.length} Grocery Order${matched.length !== 1 ? 's' : ''}`
            )}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Single regular-order card ────────────────────────────────────────────────

function OrderCard({ order, categories, onConfirm }) {
  const [items, setItems] = useState(() =>
    order.items.map((item) => ({
      ...item,
      category_id: item.suggested_category_id || null,
      subcategory_id: item.suggested_subcategory_id || null,
    }))
  )
  const [expanded, setExpanded] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)

  const updateItem = (i, field, value) => {
    setItems((prev) => {
      const next = [...prev]
      next[i] = { ...next[i], [field]: value }
      if (field === 'category_id') next[i].subcategory_id = null
      return next
    })
  }

  const allCategorized = items.every((it) => it.category_id)

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await onConfirm({
        parent_transaction_id: order.transaction_id,
        items: items.map((it) => ({
          description: it.description,
          price: it.price,
          quantity: it.quantity,
          category_id: it.category_id || null,
          subcategory_id: it.subcategory_id || null,
        })),
      })
      setConfirmed(true)
    } finally {
      setConfirming(false)
    }
  }

  if (confirmed) {
    return (
      <div className="card flex items-center gap-3 text-emerald-700 bg-emerald-50 border border-emerald-200">
        <CheckCircle size={16} />
        <span className="text-sm font-medium">
          Order {order.order_id.slice(-9)} — {items.length} item{items.length !== 1 ? 's' : ''} saved
        </span>
      </div>
    )
  }

  return (
    <div className="card p-0 overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <Package size={16} className="text-slate-400 shrink-0" />
        <span className="flex-1 text-sm font-medium text-slate-800">
          Order #{order.order_id.slice(-9)}
          <span className="ml-3 text-slate-500 font-normal">
            {order.order_date} · {formatCurrency(order.amount)} · {order.items.length} item{order.items.length !== 1 ? 's' : ''}
          </span>
        </span>
        {expanded ? <ChevronUp size={15} className="text-slate-400" /> : <ChevronDown size={15} className="text-slate-400" />}
      </button>

      {expanded && (
        <>
          <div className="overflow-x-auto border-t border-slate-100">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-left">
                  <th className="table-header">Item</th>
                  <th className="table-header">Price</th>
                  <th className="table-header">Category</th>
                  <th className="table-header">Subcategory</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="table-cell max-w-xs">
                      <span className="line-clamp-2 text-slate-700">{item.description}</span>
                    </td>
                    <td className="table-cell font-semibold tabular-nums whitespace-nowrap text-slate-800">
                      {formatCurrency(item.price)}
                    </td>
                    <td className="table-cell">
                      <CategorySelect
                        categories={categories}
                        value={item.category_id}
                        onChange={(v) => updateItem(i, 'category_id', v)}
                        disabled={confirming}
                      />
                    </td>
                    <td className="table-cell">
                      <SubcategorySelect
                        categories={categories}
                        categoryId={item.category_id}
                        value={item.subcategory_id}
                        onChange={(v) => updateItem(i, 'subcategory_id', v)}
                        disabled={confirming}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50">
            {!allCategorized && (
              <p className="text-xs text-amber-600">Assign a category to every item before confirming</p>
            )}
            <button
              onClick={handleConfirm}
              disabled={confirming || !allCategorized}
              className="btn-primary ml-auto text-sm"
            >
              {confirming ? (
                <><Loader2 size={14} className="animate-spin mr-1.5" /> Saving…</>
              ) : (
                'Confirm Order'
              )}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Amazon() {
  const { categories } = useCategories()
  const fetchAmazonUncategorizedCount = useAppStore((s) => s.fetchAmazonUncategorizedCount)
  const amazonUncategorizedCount = useAppStore((s) => s.amazonUncategorizedCount)

  const [ordersFile, setOrdersFile] = useState(null)
  const [itemsFile, setItemsFile] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)

  const handleAnalyze = async () => {
    if (!ordersFile || !itemsFile) {
      setError('Please select both CSV files.')
      return
    }
    setError(null)
    setAnalyzing(true)
    setAnalysis(null)
    try {
      const form = new FormData()
      form.append('orders_file', ordersFile)
      form.append('items_file', itemsFile)
      const { data } = await api.post('/api/amazon/analyze', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setAnalysis(data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleApplyGroceries = useCallback(async (matches) => {
    await api.post('/api/amazon/apply-groceries', { matches })
    fetchAmazonUncategorizedCount()
  }, [fetchAmazonUncategorizedCount])

  const handleItemizeOrder = useCallback(async (order) => {
    await api.post('/api/amazon/itemize', { orders: [order] })
    fetchAmazonUncategorizedCount()
  }, [fetchAmazonUncategorizedCount])

  const totalMatched =
    analysis
      ? analysis.grocery_matches.filter((m) => m.transaction_id).length +
        analysis.regular_orders.filter((o) => o.transaction_id).length
      : 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Amazon Categorizer</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          {amazonUncategorizedCount > 0
            ? `${amazonUncategorizedCount} uncategorized Amazon transaction${amazonUncategorizedCount !== 1 ? 's' : ''} — upload your order history to categorize them`
            : 'Upload your Amazon order history to categorize transactions'}
        </p>
      </div>

      {/* Upload card */}
      <div className="card space-y-4">
        <h2 className="text-base font-semibold text-slate-700">Upload Amazon Order History</h2>
        <p className="text-sm text-slate-500">
          Export both CSV files from{' '}
          <a
            href="https://www.amazon.com/your-orders/orders"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            amazon.com/your-orders
          </a>
          : the <strong>Orders</strong> file (one row per order) and the <strong>Items</strong> file
          (one row per item).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FileDropZone
            label="Orders CSV (one row per order)"
            file={ordersFile}
            onChange={setOrdersFile}
          />
          <FileDropZone
            label="Items CSV (one row per item)"
            file={itemsFile}
            onChange={setItemsFile}
          />
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            <AlertCircle size={15} />
            {error}
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={handleAnalyze}
            disabled={analyzing || !ordersFile || !itemsFile}
            className="btn-primary"
          >
            {analyzing ? (
              <><Loader2 size={15} className="animate-spin mr-1.5" /> Analyzing & suggesting categories…</>
            ) : (
              'Analyze Orders'
            )}
          </button>
        </div>
      </div>

      {/* Results */}
      {analysis && (
        <div className="space-y-4">
          {/* Summary banner */}
          <div className="card p-4 bg-indigo-50 border border-indigo-200 text-indigo-800 text-sm flex items-center gap-2">
            <CheckCircle size={16} />
            <span>
              Found <strong>{totalMatched}</strong> matching transaction{totalMatched !== 1 ? 's' : ''}
              {analysis.unmatched.length > 0 && (
                <> · <span className="text-amber-700">{analysis.unmatched.length} order{analysis.unmatched.length !== 1 ? 's' : ''} not matched</span></>
              )}
            </span>
          </div>

          {/* Grocery section */}
          {analysis.grocery_matches.length > 0 && (
            <GrocerySection
              matches={analysis.grocery_matches}
              categories={categories}
              onApply={handleApplyGroceries}
            />
          )}

          {/* Regular orders */}
          {analysis.regular_orders.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                <Package size={17} className="text-indigo-500" />
                Regular Orders — {analysis.regular_orders.length} order{analysis.regular_orders.length !== 1 ? 's' : ''}
              </h3>
              {analysis.regular_orders.map((order) => (
                <OrderCard
                  key={order.order_id}
                  order={order}
                  categories={categories}
                  onConfirm={handleItemizeOrder}
                />
              ))}
            </div>
          )}

          {/* Unmatched orders */}
          {analysis.unmatched.length > 0 && (
            <div className="card space-y-3">
              <h3 className="font-semibold text-slate-800 flex items-center gap-2">
                <AlertCircle size={17} className="text-amber-500" />
                Unmatched Orders ({analysis.unmatched.length})
              </h3>
              <p className="text-sm text-slate-500">
                These orders couldn't be matched to an existing transaction. They may have been
                imported under a different account, already categorized, or the amounts differ.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left">
                      <th className="table-header">Order ID</th>
                      <th className="table-header">Date</th>
                      <th className="table-header">Amount</th>
                      <th className="table-header">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {analysis.unmatched.map((o) => (
                      <tr key={o.order_id} className="opacity-70">
                        <td className="table-cell text-xs font-mono">{o.order_id.slice(-12)}</td>
                        <td className="table-cell text-slate-500">{o.order_date}</td>
                        <td className="table-cell tabular-nums">
                          {o.amount ? formatCurrency(o.amount) : '—'}
                        </td>
                        <td className="table-cell">
                          <span className="text-amber-600 text-xs">
                            {o.reason === 'no_transaction_found'
                              ? 'No matching transaction'
                              : o.reason === 'no_payment_amount'
                              ? 'Could not parse payment amount'
                              : o.reason}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state — no uncategorized, no analysis */}
      {!analysis && amazonUncategorizedCount === 0 && (
        <div className="card text-center py-14">
          <ShoppingCart size={44} className="mx-auto text-slate-300 mb-4" />
          <h2 className="text-lg font-semibold text-slate-700 mb-1">No uncategorized Amazon transactions</h2>
          <p className="text-slate-500 text-sm">
            Import a bank statement first, then upload your order history above to categorize any Amazon charges.
          </p>
        </div>
      )}
    </div>
  )
}
