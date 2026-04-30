import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Brain, Check, ChevronDown, ChevronRight, GripVertical, Loader2, Lock, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { useCategories } from '../hooks/useCategories'
import {
  createAccount, updateAccount, deleteAccount,
} from '../services/accountService'
import {
  createCategory, updateCategory, deleteCategory,
  createSubcategory, updateSubcategory, deleteSubcategory,
  reorderSubcategories,
} from '../services/categoryService'
import { getTrainingDataStats, trainCategorizer } from '../services/mlService'

const ACCOUNT_TYPES = ['checking', 'savings', 'credit_card', 'investment', 'cash', 'venmo', 'other']

const SIGN_CONVENTIONS = [
  { value: 'positive_expense', label: 'Positive = Expense' },
  { value: 'negative_expense', label: 'Negative = Expense' },
]

const defaultSignConvention = (type) =>
  type === 'credit_card' ? 'negative_expense' : 'positive_expense'

// ---------------------------------------------------------------------------
// Account rows
// ---------------------------------------------------------------------------

function AccountRow({ account, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    name: account.name,
    type: account.type,
    institution: account.institution || '',
    sign_convention: account.sign_convention || defaultSignConvention(account.type),
  })
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try { await onUpdate(account.id, form); setEditing(false) }
    finally { setSaving(false) }
  }

  if (editing) {
    return (
      <tr className="bg-indigo-50">
        <td className="table-cell">
          <input className="input py-1 text-sm" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder="Account name" />
        </td>
        <td className="table-cell">
          <select className="input py-1 text-sm" value={form.type} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
            {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
          </select>
        </td>
        <td className="table-cell">
          <input className="input py-1 text-sm" value={form.institution} onChange={(e) => setForm((p) => ({ ...p, institution: e.target.value }))} placeholder="Institution" />
        </td>
        <td className="table-cell">
          <select className="input py-1 text-sm" value={form.sign_convention} onChange={(e) => setForm((p) => ({ ...p, sign_convention: e.target.value }))}>
            {SIGN_CONVENTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </td>
        <td className="table-cell">
          <div className="flex gap-1">
            <button onClick={handleSave} disabled={saving} className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={15} /></button>
            <button onClick={() => setEditing(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded"><X size={15} /></button>
          </div>
        </td>
      </tr>
    )
  }

  const signLabel = account.sign_convention === 'negative_expense' ? '− Expense' : '+ Expense'
  const isVenmo = (account.type || '').toLowerCase() === 'venmo'

  return (
    <tr className="hover:bg-slate-50">
      <td className="table-cell font-medium">{account.name}</td>
      <td className="table-cell text-slate-500 capitalize">{(account.type || '').replace('_', ' ')}</td>
      <td className="table-cell text-slate-500">{account.institution || '—'}</td>
      <td className="table-cell">
        {isVenmo ? (
          <span className="text-xs text-slate-400 italic">N/A</span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">
            {signLabel}
          </span>
        )}
      </td>
      <td className="table-cell">
        <div className="flex items-center gap-1">
          <span className={`text-xs px-2 py-0.5 rounded-full ${account.is_active !== false ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
            {account.is_active !== false ? 'Active' : 'Inactive'}
          </span>
          <button onClick={() => setEditing(true)} className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded ml-1"><Pencil size={14} /></button>
          <button onClick={() => onDelete(account.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded"><Trash2 size={14} /></button>
        </div>
      </td>
    </tr>
  )
}

function AddAccountRow({ onAdd }) {
  const [form, setForm] = useState({ name: '', type: 'checking', institution: '', sign_convention: 'positive_expense' })
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)

  const handleTypeChange = (newType) => {
    setForm((p) => ({ ...p, type: newType, sign_convention: defaultSignConvention(newType) }))
  }

  const handleAdd = async () => {
    if (!form.name) return
    setSaving(true)
    try { await onAdd(form); setForm({ name: '', type: 'checking', institution: '', sign_convention: 'positive_expense' }); setOpen(false) }
    finally { setSaving(false) }
  }

  if (!open) {
    return (
      <tr>
        <td colSpan={5} className="px-4 py-2">
          <button onClick={() => setOpen(true)} className="flex items-center gap-1 text-sm text-indigo-600 hover:text-indigo-700 font-medium">
            <Plus size={15} /> Add Account
          </button>
        </td>
      </tr>
    )
  }

  return (
    <tr className="bg-indigo-50">
      <td className="table-cell"><input className="input py-1 text-sm" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder="Account name" autoFocus /></td>
      <td className="table-cell">
        <select className="input py-1 text-sm" value={form.type} onChange={(e) => handleTypeChange(e.target.value)}>
          {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
        </select>
      </td>
      <td className="table-cell"><input className="input py-1 text-sm" value={form.institution} onChange={(e) => setForm((p) => ({ ...p, institution: e.target.value }))} placeholder="Institution" /></td>
      <td className="table-cell">
        <select className="input py-1 text-sm" value={form.sign_convention} onChange={(e) => setForm((p) => ({ ...p, sign_convention: e.target.value }))}>
          {SIGN_CONVENTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </td>
      <td className="table-cell">
        <div className="flex gap-1">
          <button onClick={handleAdd} disabled={saving || !form.name} className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={15} /></button>
          <button onClick={() => setOpen(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded"><X size={15} /></button>
        </div>
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Subcategory row (edit / delete — no reorder controls here, handled by DnD)
// ---------------------------------------------------------------------------

function SubcategoryRow({ sub, dragHandleProps, onUpdate, onDelete, isDragging }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(sub.name)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try { await onUpdate(sub.id, { name }); setEditing(false) }
    finally { setSaving(false) }
  }

  return (
    <div
      className={`flex items-center gap-2 rounded px-1 transition-opacity ${isDragging ? 'opacity-40' : 'opacity-100'}`}
    >
      {/* Drag handle */}
      <span
        {...dragHandleProps}
        className="cursor-grab active:cursor-grabbing text-slate-300 hover:text-slate-500 shrink-0 touch-none"
        title="Drag to reorder"
      >
        <GripVertical size={14} />
      </span>

      <span className="w-1.5 h-1.5 rounded-full bg-slate-300 shrink-0" />

      {editing ? (
        <>
          <input
            className="input py-0.5 text-sm flex-1 max-w-xs"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            autoFocus
          />
          <button onClick={handleSave} disabled={saving} className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={13} /></button>
          <button onClick={() => { setName(sub.name); setEditing(false) }} className="p-1 text-slate-400 hover:bg-slate-100 rounded"><X size={13} /></button>
        </>
      ) : (
        <>
          <span className="text-sm text-slate-700 flex-1">{sub.name}</span>
          <button onClick={() => { setName(sub.name); setEditing(true) }} className="p-1 text-slate-400 hover:text-indigo-600 rounded"><Pencil size={12} /></button>
          <button onClick={() => onDelete(sub.id)} className="p-1 text-slate-400 hover:text-red-500 rounded"><Trash2 size={12} /></button>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drag-and-drop subcategory list
// Manages its own local ordering state; fires one API call on drag end.
// ---------------------------------------------------------------------------

function SubcategoryList({ categoryId, subcategories, onUpdateSub, onDeleteSub, onReorderSubs }) {
  const [items, setItems] = useState(subcategories)
  const draggingId = useRef(null)
  const dragOverId = useRef(null)

  // Keep in sync when the server refreshes categories
  useEffect(() => { setItems(subcategories) }, [subcategories])

  const handleDragStart = (e, id) => {
    draggingId.current = id
    e.dataTransfer.effectAllowed = 'move'
    // Minimal ghost image — browsers default to the full element which is fine
  }

  const handleDragOver = (e, id) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (id === draggingId.current || id === dragOverId.current) return
    dragOverId.current = id
    setItems((prev) => {
      const copy = [...prev]
      const fromIdx = copy.findIndex((s) => s.id === draggingId.current)
      const toIdx = copy.findIndex((s) => s.id === id)
      if (fromIdx === -1 || toIdx === -1) return prev
      const [moved] = copy.splice(fromIdx, 1)
      copy.splice(toIdx, 0, moved)
      return copy
    })
  }

  const handleDrop = (e) => {
    e.preventDefault()
    onReorderSubs(categoryId, items.map((s) => s.id))
  }

  const handleDragEnd = () => {
    draggingId.current = null
    dragOverId.current = null
  }

  return (
    <div className="space-y-1.5">
      {items.map((sub) => (
        <div
          key={sub.id}
          onDragOver={(e) => handleDragOver(e, sub.id)}
          onDrop={handleDrop}
        >
          <SubcategoryRow
            sub={sub}
            isDragging={draggingId.current === sub.id}
            dragHandleProps={{
              draggable: true,
              onDragStart: (e) => handleDragStart(e, sub.id),
              onDragEnd: handleDragEnd,
            }}
            onUpdate={onUpdateSub}
            onDelete={onDeleteSub}
          />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Category row
// ---------------------------------------------------------------------------

function CategoryRow({ category, protected: isProtected, onUpdateCat, onDeleteCat, onAddSub, onUpdateSub, onDeleteSub, onReorderSubs }) {
  const [expanded, setExpanded] = useState(false)
  const [editingCat, setEditingCat] = useState(false)
  const [catForm, setCatForm] = useState({ name: category.name, color: category.color || '#6366f1', budget_excluded: category.budget_excluded ?? false })
  const [newSubName, setNewSubName] = useState('')
  const [addingSub, setAddingSub] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSaveCat = async () => {
    setSaving(true)
    try { await onUpdateCat(category.id, catForm); setEditingCat(false) }
    finally { setSaving(false) }
  }

  const handleAddSub = async () => {
    if (!newSubName.trim()) return
    setAddingSub(true)
    try { await onAddSub(category.id, newSubName.trim()); setNewSubName('') }
    finally { setAddingSub(false) }
  }

  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50">
        <button onClick={() => setExpanded((e) => !e)} className="text-slate-400">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        {editingCat ? (
          <div className="flex items-center gap-2 flex-1 flex-wrap">
            <input type="color" value={catForm.color} onChange={(e) => setCatForm((p) => ({ ...p, color: e.target.value }))} className="w-8 h-8 rounded cursor-pointer border border-slate-200" />
            <input className="input py-1 text-sm flex-1 max-w-xs" value={catForm.name} onChange={(e) => setCatForm((p) => ({ ...p, name: e.target.value }))} autoFocus />
            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none whitespace-nowrap">
              <input
                type="checkbox"
                checked={catForm.budget_excluded}
                onChange={(e) => setCatForm((p) => ({ ...p, budget_excluded: e.target.checked }))}
                className="w-3.5 h-3.5 rounded accent-indigo-600"
              />
              Exclude from budget
            </label>
            <button onClick={handleSaveCat} disabled={saving} className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={15} /></button>
            <button onClick={() => setEditingCat(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded"><X size={15} /></button>
          </div>
        ) : (
          <div className="flex items-center gap-3 flex-1">
            <span className="w-4 h-4 rounded-full shrink-0" style={{ backgroundColor: category.color || '#94a3b8' }} />
            <span className="font-medium text-slate-800">{category.name}</span>
            <span className="text-xs text-slate-400">{(category.subcategories ?? []).length} subcategories</span>
            {category.budget_excluded && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-medium">excluded</span>
            )}
          </div>
        )}
        {!editingCat && (
          <div className="flex gap-1">
            <button
              onClick={() => { setCatForm({ name: category.name, color: category.color || '#6366f1', budget_excluded: category.budget_excluded ?? false }); setEditingCat(true) }}
              className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded"
              title="Edit category"
            >
              <Pencil size={14} />
            </button>
            {isProtected ? (
              <span title="System category — cannot be deleted" className="p-1.5 text-slate-300 cursor-not-allowed">
                <Lock size={14} />
              </span>
            ) : (
              <button onClick={() => onDeleteCat(category.id)} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded" title="Delete category">
                <Trash2 size={14} />
              </button>
            )}
          </div>
        )}
      </div>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-6 py-3 space-y-3">
          {(category.subcategories ?? []).length === 0 && (
            <p className="text-xs text-slate-400 italic">No subcategories yet.</p>
          )}
          <SubcategoryList
            categoryId={category.id}
            subcategories={category.subcategories ?? []}
            onUpdateSub={onUpdateSub}
            onDeleteSub={onDeleteSub}
            onReorderSubs={onReorderSubs}
          />
          <div className="flex items-center gap-2">
            <input
              className="input py-1 text-sm max-w-xs"
              value={newSubName}
              onChange={(e) => setNewSubName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddSub()}
              placeholder="New subcategory name"
            />
            <button onClick={handleAddSub} disabled={addingSub || !newSubName.trim()} className="btn-primary py-1.5 px-3 text-xs">
              <Plus size={13} /> Add
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Machine learning panel
// ---------------------------------------------------------------------------

function formatRelativeTime(iso) {
  if (!iso) return null
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.max(0, Math.floor((now - then) / 1000))
  if (diffSec < 60)        return 'just now'
  if (diffSec < 3600)      return `${Math.floor(diffSec / 60)} min ago`
  if (diffSec < 86400)     return `${Math.floor(diffSec / 3600)} hr ago`
  const days = Math.floor(diffSec / 86400)
  if (days < 30)           return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(iso).toLocaleDateString()
}

function bucketCategory(cat) {
  // <10 txns OR no evaluation possible → Weak (data-shortage)
  if (cat.n_transactions < 10 || cat.accuracy === null || cat.accuracy === undefined) return 'weak'
  if (cat.accuracy >= 0.80) return 'strong'
  if (cat.accuracy >= 0.60) return 'decent'
  return 'weak'
}

function CategoryAccuracyRow({ cat }) {
  const bucket = bucketCategory(cat)
  const dotColor = bucket === 'strong' ? 'bg-emerald-500'
                 : bucket === 'decent' ? 'bg-amber-500'
                 : 'bg-slate-300'
  const accDisplay =
    cat.accuracy === null || cat.accuracy === undefined || cat.n_transactions < 10
      ? '—'
      : `${Math.round(cat.accuracy * 100)}%`
  const tooFew = cat.n_transactions < 10

  return (
    <div className="flex items-center text-sm py-1">
      <span className={`w-2 h-2 rounded-full ${dotColor} shrink-0 mr-2.5`} />
      <span className="flex-1 text-slate-700 truncate">{cat.name}</span>
      <span className="w-12 text-right tabular-nums text-slate-700 font-medium">{accDisplay}</span>
      <span className="w-28 text-right text-xs text-slate-400">
        {cat.n_transactions} txn{cat.n_transactions === 1 ? '' : 's'}
        {tooFew && cat.n_transactions > 0 && <span className="text-slate-400"> · too few</span>}
      </span>
    </div>
  )
}

function MachineLearningPanel() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [training, setTraining] = useState(false)
  const [error, setError] = useState(null)
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [justTrained, setJustTrained] = useState(false)

  const loadStats = async () => {
    try {
      setError(null)
      const data = await getTrainingDataStats()
      setStats(data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load model stats')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadStats() }, [])

  const handleTrain = async () => {
    setTraining(true)
    setError(null)
    setJustTrained(false)
    try {
      await trainCategorizer()
      setJustTrained(true)
      await loadStats()
      // Hide the success badge after a few seconds
      setTimeout(() => setJustTrained(false), 4000)
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Training failed'
      setError(detail)
    } finally {
      setTraining(false)
    }
  }

  if (loading) {
    return (
      <div className="card flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 size={14} className="animate-spin" /> Loading model status…
      </div>
    )
  }

  const model = stats?.model
  const totalConfirmed = stats?.total_confirmed ?? 0
  const minRequired = stats?.thresholds?.min_train_rows ?? 30
  const canTrain = totalConfirmed >= minRequired

  // Sort categories: strong → decent → weak, by accuracy desc within each bucket
  const sortedCats = [...(stats?.categories ?? [])].sort((a, b) => {
    const ba = bucketCategory(a), bb = bucketCategory(b)
    const order = { strong: 0, decent: 1, weak: 2 }
    if (order[ba] !== order[bb]) return order[ba] - order[bb]
    return (b.accuracy ?? -1) - (a.accuracy ?? -1)
  })
  const grouped = {
    strong: sortedCats.filter((c) => bucketCategory(c) === 'strong'),
    decent: sortedCats.filter((c) => bucketCategory(c) === 'decent'),
    weak:   sortedCats.filter((c) => bucketCategory(c) === 'weak'),
  }

  return (
    <div className="card">
      <div className="flex items-start gap-2 mb-4">
        <Brain size={16} className="text-indigo-500 mt-0.5 shrink-0" />
        <div className="flex-1">
          <h2 className="font-semibold text-slate-700 text-base">Machine Learning</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Local categorization model. Improves as you confirm more transactions — retrain to pick up your latest corrections.
          </p>
        </div>
      </div>

      {/* Status line */}
      <div className="flex items-center justify-between flex-wrap gap-3 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
        <div className="text-sm text-slate-700">
          {model?.trained ? (
            <>
              Trained <span className="font-medium">{formatRelativeTime(model.trained_at)}</span>
              {' · '}
              <span className="font-medium">{model.n_samples}</span> transactions
              {' · '}
              <span className="font-medium">{Math.round((model.accuracy ?? 0) * 100)}%</span> accurate
            </>
          ) : (
            <>
              No model trained yet.
              {totalConfirmed > 0 && (
                <span className="text-slate-500"> {totalConfirmed} transactions ready to train on.</span>
              )}
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          {justTrained && (
            <span className="text-xs text-emerald-600 font-medium flex items-center gap-1">
              <Check size={13} /> Done
            </span>
          )}
          <button
            onClick={handleTrain}
            disabled={training || !canTrain}
            className="btn-primary py-1.5 px-3 text-sm"
            title={!canTrain ? `Need at least ${minRequired} confirmed transactions (have ${totalConfirmed})` : ''}
          >
            {training ? (
              <><Loader2 size={14} className="animate-spin" /> Training…</>
            ) : (
              model?.trained ? 'Retrain' : 'Train Model'
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-start gap-2">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Helpful hint when below the training threshold */}
      {!canTrain && !error && (
        <div className="mt-3 text-xs text-slate-500">
          Need at least <span className="font-medium">{minRequired}</span> confirmed transactions before training.
          You have <span className="font-medium">{totalConfirmed}</span>.
        </div>
      )}

      {/* Per-category breakdown */}
      {model?.trained && sortedCats.length > 0 && (
        <div className="mt-4">
          <button
            onClick={() => setShowBreakdown((v) => !v)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 font-medium"
          >
            {showBreakdown ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {showBreakdown ? 'Hide' : 'Show'} per-category breakdown
          </button>

          {showBreakdown && (
            <div className="mt-3 space-y-4">
              {grouped.strong.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700 mb-1.5">
                    Strong  <span className="text-slate-400 normal-case font-normal">(&gt;80% accuracy)</span>
                  </h3>
                  <div className="divide-y divide-slate-100">
                    {grouped.strong.map((c) => <CategoryAccuracyRow key={c.id} cat={c} />)}
                  </div>
                </div>
              )}
              {grouped.decent.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-amber-700 mb-1.5">
                    Decent  <span className="text-slate-400 normal-case font-normal">(60–80%)</span>
                  </h3>
                  <div className="divide-y divide-slate-100">
                    {grouped.decent.map((c) => <CategoryAccuracyRow key={c.id} cat={c} />)}
                  </div>
                </div>
              )}
              {grouped.weak.length > 0 && (
                <div>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                    Weak — needs more data  <span className="text-slate-400 normal-case font-normal">(&lt;60% or &lt;10 txns)</span>
                  </h3>
                  <div className="divide-y divide-slate-100">
                    {grouped.weak.map((c) => <CategoryAccuracyRow key={c.id} cat={c} />)}
                  </div>
                </div>
              )}
              {stats?.user_corrections > 0 && (
                <p className="text-xs text-slate-400 pt-2 border-t border-slate-100">
                  The model weights your <span className="font-medium">{stats.user_corrections}</span> corrections 3× more than uncorrected confirmations.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Settings() {
  const accounts = useAppStore((s) => s.accounts)
  const fetchAccounts = useAppStore((s) => s.fetchAccounts)
  const fetchCategories = useAppStore((s) => s.fetchCategories)
  const { categories } = useCategories()

  const [newCatForm, setNewCatForm] = useState({ name: '', color: '#6366f1' })
  const [addingCat, setAddingCat] = useState(false)
  const [error, setError] = useState(null)

  const regularCats = categories.filter((c) => !c.budget_excluded)
  const systemCats  = categories.filter((c) => c.budget_excluded)

  const handleAddAccount    = async (data) => { await createAccount({ ...data, is_active: true }); await fetchAccounts() }
  const handleUpdateAccount = async (id, data) => { await updateAccount(id, data); await fetchAccounts() }
  const handleDeleteAccount = async (id) => { await deleteAccount(id); await fetchAccounts() }

  const handleAddCategory = async () => {
    if (!newCatForm.name.trim()) return
    setAddingCat(true)
    try { await createCategory(newCatForm); await fetchCategories(); setNewCatForm({ name: '', color: '#6366f1' }) }
    finally { setAddingCat(false) }
  }

  const handleUpdateCategory    = async (id, data) => { await updateCategory(id, data); await fetchCategories() }
  const handleDeleteCategory    = async (id) => { await deleteCategory(id); await fetchCategories() }
  const handleAddSubcategory    = async (categoryId, name) => { await createSubcategory({ category_id: categoryId, name }); await fetchCategories() }
  const handleUpdateSubcategory = async (id, data) => { await updateSubcategory(id, data); await fetchCategories() }
  const handleDeleteSubcategory = async (id) => { await deleteSubcategory(id); await fetchCategories() }
  const handleReorderSubs       = async (categoryId, ids) => { await reorderSubcategories(categoryId, ids); await fetchCategories() }

  const sharedCatProps = {
    onUpdateCat: handleUpdateCategory,
    onDeleteCat: handleDeleteCategory,
    onAddSub: handleAddSubcategory,
    onUpdateSub: handleUpdateSubcategory,
    onDeleteSub: handleDeleteSubcategory,
    onReorderSubs: handleReorderSubs,
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Settings</h1>
        <p className="text-slate-500 text-sm mt-0.5">Manage accounts and categories</p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
      )}

      {/* Accounts */}
      <div className="card p-0 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-700 text-base">Accounts</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="table-header">Name</th>
              <th className="table-header">Type</th>
              <th className="table-header">Institution</th>
              <th className="table-header">Sign Convention</th>
              <th className="table-header">Status / Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {accounts.map((account) => (
              <AccountRow key={account.id} account={account} onUpdate={handleUpdateAccount} onDelete={handleDeleteAccount} />
            ))}
            <AddAccountRow onAdd={handleAddAccount} />
          </tbody>
        </table>
      </div>

      {/* Regular categories */}
      <div className="card">
        <div className="mb-4">
          <h2 className="font-semibold text-slate-700 text-base">Categories</h2>
          <p className="text-xs text-slate-400 mt-0.5">Budget categories tracked in your spending summary. Drag the ⠿ handle to reorder subcategories.</p>
        </div>

        <div className="space-y-2 mb-4">
          {regularCats.length === 0 && (
            <p className="text-slate-400 text-sm">No categories yet. Add one below.</p>
          )}
          {regularCats.map((cat) => (
            <CategoryRow key={cat.id} category={cat} protected={false} {...sharedCatProps} />
          ))}
        </div>

        <div className="border border-dashed border-slate-300 rounded-lg p-4">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Add Category</p>
          <div className="flex items-center gap-3">
            <input type="color" value={newCatForm.color} onChange={(e) => setNewCatForm((p) => ({ ...p, color: e.target.value }))} className="w-10 h-10 rounded-lg cursor-pointer border border-slate-200" />
            <input
              className="input flex-1 max-w-xs"
              value={newCatForm.name}
              onChange={(e) => setNewCatForm((p) => ({ ...p, name: e.target.value }))}
              onKeyDown={(e) => e.key === 'Enter' && handleAddCategory()}
              placeholder="Category name"
            />
            <button onClick={handleAddCategory} disabled={addingCat || !newCatForm.name.trim()} className="btn-primary">
              <Plus size={16} /> Add Category
            </button>
          </div>
        </div>
      </div>

      {/* Machine Learning */}
      <MachineLearningPanel />

      {/* System categories (Income, Investments) */}
      {systemCats.length > 0 && (
        <div className="card">
          <div className="flex items-start gap-2 mb-4">
            <Lock size={15} className="text-slate-400 mt-0.5 shrink-0" />
            <div>
              <h2 className="font-semibold text-slate-700 text-base">System Categories</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Used by the budget engine — cannot be deleted. You can rename them, change their colour, and add subcategories.
              </p>
            </div>
          </div>
          <div className="space-y-2">
            {systemCats.map((cat) => (
              <CategoryRow key={cat.id} category={cat} protected={true} {...sharedCatProps} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
