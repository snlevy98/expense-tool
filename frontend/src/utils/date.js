import { format, parseISO } from 'date-fns'

export const formatDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : dateStr
    return format(date, 'MMM d, yyyy')
  } catch {
    return dateStr
  }
}

export const formatMonth = (month, year) => {
  const date = new Date(year, month - 1, 1)
  return format(date, 'MMMM yyyy')
}

export const getMonthName = (month) => {
  const date = new Date(2000, month - 1, 1)
  return format(date, 'MMMM')
}

export const getCurrentMonthYear = () => {
  const now = new Date()
  return {
    month: now.getMonth() + 1,
    year: now.getFullYear(),
  }
}

export const toInputDate = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = typeof dateStr === 'string' ? parseISO(dateStr) : dateStr
    return format(date, 'yyyy-MM-dd')
  } catch {
    return dateStr
  }
}
