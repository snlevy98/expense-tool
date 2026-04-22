import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { useCategories } from '../hooks/useCategories'
import { useAppStore } from '../store/appStore'
import { toInputDate } from '../utils/date'

export default function EditTransactionModal({ transaction, onSave, onClose }) {
  const { categories, getSubcategories } = useCategories()
  const accounts = useAppStore((s) => s.accounts)

  const [form, setForm] = useState({
    merchant_name: '',
    transaction_date: '',
    amount: '',
    category_id: '',
    subcategory_id: '',
    account_id: '',
    notes: '',
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (transaction) {
      setForm({
        merchant_name: transaction.merchant_name || transaction.description || '',
        transaction_date: toInputDate(transaction.transaction_date),
        amount: transaction.amount != null ? String(Math.abs(parseFloat(transaction.amount))) : '',
        category_id: transaction.category_id || '',
        subcategory_id: transaction.subcategory_id || '',
        account_id: transaction.account_id || '',
        notes: transaction.notes || '',
      })
    }
  }, [transaction])

  const subcategories = getSubcategories(form.category_id)

  const handleChange = (key, value) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value }
      if (key === 'category_id') next.subcategory_id = ''
      return next
    })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onSave(transaction.id, {
        ...form,
        amount: parseFloat(form.amount),
        category_id: form.category_id || null,
        subcategory_id: form.subcategory_id || null,
        account_id: form.account_id || null,
      })
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-800">Edit Transaction</h2>
          <button onClick={onClose} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
          )}

          <div>
            <label className="label">Merchant / Description</label>
            <input
              className="input"
              value={form.merchant_name}
              onChange={(e) => handleChange('merchant_name', e.target.value)}
              placeholder="Merchant name"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Date</label>
              <input
                type="date"
                className="input"
                value={form.transaction_date}
                onChange={(e) => handleChange('transaction_date', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="label">Amount</label>
              <input
                type="number"
                step="0.01"
                min="0"
                className="input"
                value={form.amount}
                onChange={(e) => handleChange('amount', e.target.value)}
                placeholder="0.00"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Category</label>
              <select
                className="input"
                value={form.category_id}
                onChange={(e) => handleChange('category_id', e.target.value)}
              >
                <option value="">— None —</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Subcategory</label>
              <select
                className="input"
                value={form.subcategory_id}
                onChange={(e) => handleChange('subcategory_id', e.target.value)}
                disabled={!form.category_id || subcategories.length === 0}
              >
                <option value="">— None —</option>
                {subcategories.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="label">Account</label>
            <select
              className="input"
              value={form.account_id}
              onChange={(e) => handleChange('account_id', e.target.value)}
            >
              <option value="">— None —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label">Notes</label>
            <textarea
              className="input resize-none"
              rows={2}
              value={form.notes}
              onChange={(e) => handleChange('notes', e.target.value)}
              placeholder="Optional notes..."
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
