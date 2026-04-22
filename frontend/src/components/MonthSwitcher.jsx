import { ChevronLeft, ChevronRight } from 'lucide-react'
import { formatMonth } from '../utils/date'

export default function MonthSwitcher({ month, year, onChange }) {
  const handlePrev = () => {
    if (month === 1) {
      onChange(12, year - 1)
    } else {
      onChange(month - 1, year)
    }
  }

  const handleNext = () => {
    if (month === 12) {
      onChange(1, year + 1)
    } else {
      onChange(month + 1, year)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handlePrev}
        className="p-1.5 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
        aria-label="Previous month"
      >
        <ChevronLeft size={20} />
      </button>
      <span className="text-lg font-semibold text-slate-800 min-w-[160px] text-center">
        {formatMonth(month, year)}
      </span>
      <button
        onClick={handleNext}
        className="p-1.5 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
        aria-label="Next month"
      >
        <ChevronRight size={20} />
      </button>
    </div>
  )
}
