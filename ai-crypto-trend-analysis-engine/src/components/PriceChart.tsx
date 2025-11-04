
import React from 'react';
import { AreaChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Kline } from '../types';
import { formatPrice } from '../utils/formatters';

interface PriceChartProps {
  data: Kline[];
  signal: 'BUY' | 'SELL' | 'HOLD';
}

const PriceChart: React.FC<PriceChartProps> = ({ data, signal }) => {
  const chartData = data.map(k => ({
    time: new Date(k.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    price: k.close
  }));

  const getStrokeColor = () => {
    switch (signal) {
      case 'BUY':
        return { from: '#10B981', to: '#6EE7B7' }; // Green
      case 'SELL':
        return { from: '#EF4444', to: '#F87171' }; // Red
      default:
        return { from: '#6B7280', to: '#9CA3AF' }; // Gray
    }
  };

  const colors = getStrokeColor();

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart
        data={chartData}
        margin={{ top: 5, right: 20, left: -10, bottom: 5 }}
      >
        <defs>
          <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={colors.from} stopOpacity={0.8}/>
            <stop offset="95%" stopColor={colors.from} stopOpacity={0}/>
          </linearGradient>
        </defs>
        <XAxis 
          dataKey="time" 
          tick={{ fill: '#6B7280', fontSize: 12 }} 
          axisLine={{ stroke: '#4B5563' }}
          tickLine={{ stroke: '#4B5563' }}
        />
        <YAxis 
          domain={['auto', 'auto']} 
          tick={{ fill: '#6B7280', fontSize: 12 }} 
          axisLine={{ stroke: '#4B5563' }}
          tickLine={{ stroke: '#4B5563' }}
          tickFormatter={(value) => formatPrice(value)}
          width={80}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(20, 20, 30, 0.8)',
            borderColor: '#4B5563',
            color: '#D1D5DB',
          }}
          labelStyle={{ color: '#9CA3AF' }}
          formatter={(value: number) => [formatPrice(value), 'Price']}
        />
        <Area 
            type="monotone" 
            dataKey="price" 
            stroke="transparent" 
            fill="url(#colorPrice)" 
        />
        <Line 
          type="monotone" 
          dataKey="price" 
          stroke={colors.from} 
          strokeWidth={2}
          dot={false} 
        />
      </AreaChart>
    </ResponsiveContainer>
  );
};

export default PriceChart;
