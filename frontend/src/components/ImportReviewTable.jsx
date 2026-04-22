import { useCategories } from '../hooks/useCategories'

export default function ImportReviewTable({ items, onUpdate }) {
  const { categories, getSubcategories } = useCategories()

  if (!items || items.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">No transactions to review.</div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="table-header w-10">
              <input
                type="checkbox"
                className="rounded border-slate-300"
                checked={items.every((item) => item.include !== false)}
                onChange={(e) =>
                  items.forEach((_, i) => onUpdate(i, 'include', e.target.checked))
                }
              />
            </th>
            <th className="table-header">Date</th>
            <th className="table-header">Description</th>
            <th className="table-header">Merchant</th>
            <th className="table-header">Amount</th>
            <th className="table-header">Category</th>
            <th className="table-header">Subcategory</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((item, index) => {
            const isIncluded = item.include !== false
            const subcategories = getSubcategories(item.category_id)

            return (
              <tr
                key={index}
                className={`transition-colors ${isIncluded ? 'hover:bg-slate-50' : 'opacity-40 bg-slate-50'}`}
              >
                <td className="table-cell">
                  <input
                    type="checkbox"
                    className="rounded border-slate-300"
                    checked={isIncluded}
                    onChange={(e) => onUpdate(index, 'include', e.target.checked)}
                  />
                </td>
                <td className="table-cell text-slate-500 whitespace-nowrap">
                  {item.transaction_date || item.date || '—'}
                </td>
                <td className="table-cell max-w-[200px] truncate text-slate-600" title={item.raw_description}>
                  {item.raw_description || '—'}
                </td>
                <td className="table-cell">
                  <input
                    className="input py-1 text-xs min-w-[130px]"
                    value={item.merchant_name || ''}
                    onChange={(e) => onUpdate(index, 'merchant_name', e.target.value)}
                    disabled={!isIncluded}
                    placeholder="Merchant name"
                  />
                </td>
                <td className={`table-cell font-medium tabular-nums whitespace-nowrap ${parseFloat(item.amount) < 0 ? 'text-emerald-600' : 'text-slate-800'}`}>
                  {parseFloat(item.amount) < 0 ? '+' : ''}$
                  {Math.abs(parseFloat(item.amount) || 0).toFixed(2)}
                </td>
                <td className="table-cell">
                  <select
                    className="input py-1 text-xs min-w-[140px]"
                    value={item.category_id || ''}
                    onChange={(e) => {
                      onUpdate(index, 'category_id', e.target.value)
                      onUpdate(index, 'subcategory_id', '')
                    }}
                    disabled={!isIncluded}
                  >
                    <option value="">— None —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </td>
                <td className="table-cell">
                  <select
                    className="input py-1 text-xs min-w-[140px]"
                    value={item.subcategory_id || ''}
                    onChange={(e) => onUpdate(index, 'subcategory_id', e.target.value)}
                    disabled={!isIncluded || !item.category_id || subcategories.length === 0}
                  >
                    <option value="">— None —</option>
                    {subcategories.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
