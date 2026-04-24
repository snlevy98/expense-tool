import { useState, useRef, useEffect, useCallback } from 'react'
import { Upload, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import ImportReviewTable from '../components/ImportReviewTable'
import { useAppStore } from '../store/appStore'
import { api } from '../services/api'

const STEPS = ['Select File', 'Review', 'Confirm']
const ENRICH_BATCH_SIZE = 15
const MAX_RETRIES = 5

function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-0">
      {STEPS.map((label, i) => (
        <div key={i} className="flex items-center">
          <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold transition-colors ${
            i < current
              ? 'bg-indigo-600 text-white'
              : i === current
              ? 'bg-indigo-100 text-indigo-700 border-2 border-indigo-600'
              : 'bg-slate-100 text-slate-400'
          }`}>
            {i < current ? <CheckCircle size={16} /> : i + 1}
          </div>
          <span className={`ml-2 text-sm font-medium ${i === current ? 'text-indigo-700' : i < current ? 'text-slate-600' : 'text-slate-400'}`}>
            {label}
          </span>
          {i < STEPS.length - 1 && (
            <div className={`mx-4 h-0.5 w-12 ${i < current ? 'bg-indigo-600' : 'bg-slate-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

export default function Import() {
  const accounts = useAppStore((s) => s.accounts)
  const fetchUncategorizedCount = useAppStore((s) => s.fetchUncategorizedCount)

  const [step, setStep] = useState(0)
  const [accountId, setAccountId] = useState('')
  const [lastTxDate, setLastTxDate] = useState(null)
  const [file, setFile] = useState(null)
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  // Enrichment state
  const [enrichStatus, setEnrichStatus] = useState('idle') // 'idle' | 'running' | 'retrying' | 'done'
  const [enrichProgress, setEnrichProgress] = useState({ processed: 0, total: 0 })
  const [retryCountdown, setRetryCountdown] = useState(0)
  const abortEnrichRef = useRef(false)

  const fileInputRef = useRef()

  useEffect(() => {
    if (!accountId) { setLastTxDate(null); return }
    api.get(`/api/accounts/${accountId}/last-transaction-date`)
      .then(({ data }) => setLastTxDate(data.last_transaction_date))
      .catch(() => setLastTxDate(null))
  }, [accountId])

  // Stop enrichment on unmount
  useEffect(() => () => { abortEnrichRef.current = true }, [])

  const handleFileChange = (e) => {
    const f = e.target.files[0]
    if (f) setFile(f)
  }

  // ---- Progressive AI enrichment ----

  const processBatch = useCallback(async (batch, retryCount = 0) => {
    if (abortEnrichRef.current) return
    try {
      const { data } = await api.post('/api/import/enrich', {
        transactions: batch.map((item) => ({
          index: item.index,
          raw_description: item.raw_description,
          merchant_name: item.merchant_name,
          amount: String(item.amount),
        })),
      })
      setItems((prev) => {
        const next = [...prev]
        for (const result of data.results) {
          const i = result.index
          if (i >= 0 && i < next.length) {
            next[i] = {
              ...next[i],
              merchant_name: result.merchant_name || next[i].merchant_name,
              ai_suggested_category_id: result.ai_suggested_category_id ?? null,
              ai_suggested_subcategory_id: result.ai_suggested_subcategory_id ?? null,
            }
          }
        }
        return next
      })
    } catch (err) {
      if (abortEnrichRef.current) return
      const httpStatus = err.response?.status
      if ((httpStatus === 429 || httpStatus === 503) && retryCount < MAX_RETRIES) {
        const delaySec = Math.pow(2, retryCount) * 2  // 2, 4, 8, 16, 32 s
        setEnrichStatus('retrying')
        for (let t = delaySec; t > 0; t--) {
          if (abortEnrichRef.current) return
          setRetryCountdown(t)
          await new Promise((r) => setTimeout(r, 1000))
        }
        setEnrichStatus('running')
        setRetryCountdown(0)
        return processBatch(batch, retryCount + 1)
      }
      console.error('Enrichment batch failed permanently:', err)
    }
  }, [])

  const runEnrichment = useCallback(async (allItems) => {
    abortEnrichRef.current = false
    setEnrichStatus('running')
    setEnrichProgress({ processed: 0, total: allItems.length })

    for (let start = 0; start < allItems.length; start += ENRICH_BATCH_SIZE) {
      if (abortEnrichRef.current) return
      const batch = allItems.slice(start, start + ENRICH_BATCH_SIZE)
      await processBatch(batch)
      if (!abortEnrichRef.current) {
        setEnrichProgress({ processed: start + batch.length, total: allItems.length })
      }
    }

    if (!abortEnrichRef.current) setEnrichStatus('done')
  }, [processBatch])

  // ---- Import flow ----

  const handlePreview = async () => {
    if (!accountId) { setError('Please select an account.'); return }
    if (!file) { setError('Please select a file.'); return }
    setError(null)
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('account_id', accountId)
      const { data } = await api.post('/api/import/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const previewItems = Array.isArray(data) ? data : (data.transactions ?? [])
      const enrichableItems = previewItems.map((item) => ({ ...item, include: true }))
      setItems(enrichableItems)
      setStats({ duplicates_skipped: data.duplicates_skipped ?? 0 })
      setStep(1)
      runEnrichment(enrichableItems)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Preview failed')
    } finally {
      setLoading(false)
    }
  }

  const handleUpdate = (index, field, value) => {
    setItems((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const handleConfirm = async () => {
    setError(null)
    setLoading(true)
    abortEnrichRef.current = true  // stop enrichment before confirming
    try {
      const toImport = items
        .filter((item) => item.include !== false)
        .map(({ include, index, is_duplicate, ...rest }) => ({
          ...rest,
          account_id: accountId,
          category_id: null,
          subcategory_id: null,
        }))
      await api.post('/api/import/confirm', { transactions: toImport })
      fetchUncategorizedCount()   // refresh the badge on the Categorize tab
      setSuccess(true)
      setStep(2)
    } catch (err) {
      const detail = err.response?.data?.detail
      const message =
        Array.isArray(detail)
          ? detail.map((e) => e.msg || JSON.stringify(e)).join('; ')
          : typeof detail === 'string'
          ? detail
          : err.message || 'Import failed'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    abortEnrichRef.current = true
    setStep(0)
    setFile(null)
    setItems([])
    setStats(null)
    setSuccess(false)
    setError(null)
    setAccountId('')
    setLastTxDate(null)
    setEnrichStatus('idle')
    setEnrichProgress({ processed: 0, total: 0 })
    setRetryCountdown(0)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const includedCount = items.filter((i) => i.include !== false).length

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Import Transactions</h1>
        <p className="text-slate-500 text-sm mt-0.5">Upload a CSV or Excel file to import transactions</p>
      </div>

      <div className="card">
        <StepIndicator current={step} />
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {/* Step 0: Select file */}
      {step === 0 && (
        <div className="card space-y-4">
          <h2 className="text-base font-semibold text-slate-700">Step 1: Select Account & File</h2>

          <div>
            <label className="label">Account</label>
            <div className="flex items-center gap-3">
              <select
                className="input max-w-sm"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
              >
                <option value="">— Select Account —</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              {accountId && (
                <span className="text-sm text-slate-500 whitespace-nowrap">
                  {lastTxDate
                    ? <>Last import: <span className="font-medium text-slate-700">{new Date(lastTxDate + 'T00:00:00').toLocaleDateString()}</span></>
                    : 'No transactions yet'}
                </span>
              )}
            </div>
          </div>

          <div>
            <label className="label">File</label>
            <div
              className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-indigo-400 transition-colors cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload size={32} className="mx-auto text-slate-400 mb-3" />
              {file ? (
                <div>
                  <p className="font-medium text-slate-700">{file.name}</p>
                  <p className="text-sm text-slate-400 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <div>
                  <p className="text-slate-600 font-medium">Click to upload or drag and drop</p>
                  <p className="text-sm text-slate-400 mt-1">CSV, Excel (.xlsx, .xls)</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={handleFileChange}
              />
            </div>
          </div>

          <div className="flex justify-end">
            <button onClick={handlePreview} disabled={loading || !file || !accountId} className="btn-primary">
              {loading ? 'Processing...' : 'Preview Import'}
            </button>
          </div>
        </div>
      )}

      {/* Step 1: Review */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="card p-4 flex items-center justify-between">
            <div className="text-sm text-slate-600">
              <span className="font-semibold text-slate-800">{items.length}</span> transactions found
              {stats?.duplicates_skipped > 0 && (
                <span className="ml-3 text-amber-600">
                  {stats.duplicates_skipped} duplicate{stats.duplicates_skipped !== 1 ? 's' : ''} skipped
                </span>
              )}
              <span className="ml-3 text-indigo-600 font-medium">{includedCount} selected</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => { abortEnrichRef.current = true; setStep(0) }}
                className="btn-secondary text-sm"
              >
                Back
              </button>
              <button onClick={handleConfirm} disabled={loading || includedCount === 0} className="btn-primary">
                {loading ? 'Importing...' : `Confirm Import (${includedCount})`}
              </button>
            </div>
          </div>

          {/* AI enrichment status */}
          {enrichStatus !== 'idle' && (
            <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium ${
              enrichStatus === 'done'
                ? 'bg-emerald-50 text-emerald-700'
                : enrichStatus === 'retrying'
                ? 'bg-amber-50 text-amber-700'
                : 'bg-indigo-50 text-indigo-700'
            }`}>
              {enrichStatus === 'done' ? (
                <><CheckCircle size={15} /> AI enrichment complete — merchant names and category suggestions are ready</>
              ) : enrichStatus === 'retrying' ? (
                <><AlertCircle size={15} /> Rate limited — retrying in {retryCountdown}s…</>
              ) : (
                <><Loader2 size={15} className="animate-spin" /> Enriching with AI: {enrichProgress.processed} / {enrichProgress.total} transactions</>
              )}
            </div>
          )}

          <div className="card p-0 overflow-hidden">
            <ImportReviewTable items={items} onUpdate={handleUpdate} />
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={() => { abortEnrichRef.current = true; setStep(0) }}
              className="btn-secondary"
            >
              Back
            </button>
            <button onClick={handleConfirm} disabled={loading || includedCount === 0} className="btn-primary">
              {loading ? 'Importing...' : `Confirm Import (${includedCount})`}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Success */}
      {step === 2 && (
        <div className="card text-center py-12">
          <CheckCircle size={48} className="mx-auto text-emerald-500 mb-4" />
          <h2 className="text-xl font-semibold text-slate-800 mb-2">Import Successful!</h2>
          <p className="text-slate-500 mb-6">
            {includedCount} transaction{includedCount !== 1 ? 's' : ''} have been imported successfully.
          </p>
          <button onClick={handleReset} className="btn-primary">
            Import More Transactions
          </button>
        </div>
      )}
    </div>
  )
}
