export const formatCurrency = (amount) => {
  if (amount === null || amount === undefined) return '$0.00'
  const num = parseFloat(amount)
  if (isNaN(num)) return '$0.00'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

export const formatAmount = (amount) => {
  const num = parseFloat(amount)
  if (isNaN(num)) return { text: '$0.00', isNegative: false }
  return {
    text: formatCurrency(Math.abs(num)),
    isNegative: num < 0,
    isPositive: num > 0,
  }
}

export const parseAmount = (str) => {
  if (!str) return 0
  const cleaned = String(str).replace(/[$,\s]/g, '')
  return parseFloat(cleaned) || 0
}
