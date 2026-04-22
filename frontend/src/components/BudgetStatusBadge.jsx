const STATUS_STYLES = {
  green: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
  yellow: 'bg-amber-100 text-amber-700 border border-amber-200',
  red: 'bg-red-100 text-red-700 border border-red-200',
  default: 'bg-slate-100 text-slate-600 border border-slate-200',
}

const STATUS_LABELS = {
  green: 'On Track',
  yellow: 'Near Limit',
  red: 'Over Budget',
}

export default function BudgetStatusBadge({ status }) {
  const normalized = status?.toLowerCase() ?? 'default'
  const style = STATUS_STYLES[normalized] ?? STATUS_STYLES.default
  const label = STATUS_LABELS[normalized] ?? status ?? 'Unknown'

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${style}`}>
      <span
        className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
          normalized === 'green'
            ? 'bg-emerald-500'
            : normalized === 'yellow'
            ? 'bg-amber-500'
            : normalized === 'red'
            ? 'bg-red-500'
            : 'bg-slate-400'
        }`}
      />
      {label}
    </span>
  )
}
