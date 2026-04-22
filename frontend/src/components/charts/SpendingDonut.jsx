import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts'
import { formatCurrency } from '../../utils/currency'

const RADIAN = Math.PI / 180

function CenterLabel({ viewBox, total }) {
  const { cx, cy } = viewBox
  return (
    <g>
      <text x={cx} y={cy - 8} textAnchor="middle" fill="#1e293b" className="text-sm font-semibold" fontSize={13}>
        Total
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#1e293b" fontWeight={700} fontSize={16}>
        {formatCurrency(total)}
      </text>
    </g>
  )
}

export default function SpendingDonut({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
        No spending data available.
      </div>
    )
  }

  const total = data.reduce((sum, d) => sum + (d.value || 0), 0)

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={75}
          outerRadius={110}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color || '#6366f1'} />
          ))}
          <CenterLabel total={total} />
        </Pie>
        <Tooltip
          formatter={(value) => [formatCurrency(value), 'Spent']}
          contentStyle={{
            borderRadius: '8px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
          }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => (
            <span style={{ color: '#475569', fontSize: '12px' }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
