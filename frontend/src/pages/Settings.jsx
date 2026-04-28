import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronRight, GripVertical, Lock, Pencil, Plus, Trash2, X } from 'lucide-react'
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

const ACCOUNT_TYPES = ['checking', 'savings', 'credit_card', 'investment', 'cash', 'other']

// ---------------------------------------------------------------------------
// Account rows
// ---------------------------------------------------------------------------

function AccountRow({ account, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: account.name, type: account.type, institution: account.institution || '' })
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
          <div className="flex gap-1">
            <button onClick={handleSave} disabled={saving} className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={15} /></button>
            <button onClick={() => setEditing(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded"><X size={15} /></button>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr className="hover:bg-slate-50">
      <td className="table-cell font-medium">{account.name}</td>
      <td className="table-cell text-slate-500 capitalize">{(account.type || '').replace('_', ' ')}</td>
      <td className="table-cell text-slate-500">{account.institution || '—'}</td>
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
  const [form, setForm] = useState({ name: '', type: 'checking', institution: '' })
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)

  const handleAdd = async () => {
    if (!form.name) return
    setSaving(true)
    try { await onAdd(form); setForm({ name: '', type: 'checking', institution: '' }); setOpen(false) }
    finally { setSaving(false) }
  }

  if (!open) {
    return (
      <tr>
        <td colSpan={4} className="px-4 py-2">
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
        <select className="input py-1 text-sm" value={form.type} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
          {ACCOUNT_TYPES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
        </select>
      </td>
      <td className="table-cell"><input className="input py-1 text-sm" value={form.institution} onChange={(e) => setForm((p) => ({ ...p, institution: e.target.value }))} placeholder="Institution" /></td>
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
  const [catForm, setCatForm] = useState({ name: category.name, color: category.color || '#6366f1' })
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
          <div className="flex items-center gap-2 flex-1">
            <input type="color" value={catForm.color} onChange={(e) => setCatForm((p) => ({ ...p, color: e.target.value }))} className="w-8 h-8 rounded cursor-pointer border border-slate-200" />
            <input className="input py-1 text-sm flex-1 max-w-xs" value={catForm.name} onChange={(e) => setCatForm((p) => ({ ...p, name: e.target.value }))} autoFocus />
            <button onClick={handleSaveCat} disabled={saving} className="p-1.5 text-emerald-600 hover:bg-emerald-50 rounded"><Check size={15} /></button>
            <button onClick={() => setEditingCat(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded"><X size={15} /></button>
          </div>
        ) : (
          <div className="flex items-center gap-3 flex-1">
            <span className="w-4 h-4 rounded-full shrink-0" style={{ backgroundColor: category.color || '#94a3b8' }} />
            <span className="font-medium text-slate-800">{category.name}</span>
            <span className="text-xs text-slate-400">{(category.subcategories ?? []).length} subcategories</span>
          </div>
        )}
        {!editingCat && (
          <div className="flex gap-1">
            <button
              onClick={() => { setCatForm({ name: category.name, color: category.color || '#6366f1' }); setEditingCat(true) }}
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
