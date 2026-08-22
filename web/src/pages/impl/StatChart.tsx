import React from "react";

interface ChartPoint {
  label: string;
  value: number;
}

export interface ChartSeries {
  key: string;
  label: string;
  color: string;
  points: ChartPoint[];
  fill?: boolean;
}

interface StatChartProps {
  series: ChartSeries[];
  height?: number;
  valueFormatter?: (value: number) => string;
}

/**
 * 轻量 SVG 折线图 (无第三方依赖):
 * 折线/面积用归一化 viewBox 绘制 (preserveAspectRatio=none 铺满),
 * 轴标签用 HTML 绝对定位, 避免文字随 SVG 拉伸变形。
 */
export const StatChart: React.FC<StatChartProps> = ({
  series,
  height = 168,
  valueFormatter = (value) => String(value),
}) => {
  const allValues: number[] = series.flatMap((s) => s.points.map((p) => p.value));
  const maxValue: number = Math.max(1, ...allValues);
  const pointCount: number = Math.max(2, ...series.map((s) => s.points.length));

  const toPath = (points: ChartPoint[]): string =>
    points
      .map((point, index) => {
        const x: number = pointCount <= 1 ? 0 : (index / (pointCount - 1)) * 100;
        const y: number = 96 - (point.value / maxValue) * 88;
        return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");

  const toArea = (points: ChartPoint[]): string => {
    if (points.length === 0) return "";
    const line = toPath(points);
    const lastX: number = pointCount <= 1 ? 0 : ((points.length - 1) / (pointCount - 1)) * 100;
    return `${line} L${lastX.toFixed(2)},96 L0,96 Z`;
  };

  const tickIndexes: number[] =
    pointCount <= 8
      ? Array.from({ length: pointCount }, (_, i) => i)
      : [0, Math.floor(pointCount / 2), pointCount - 1];
  const tickLabels: string[] = tickIndexes.map((index) => {
    const label = series[0]?.points[index]?.label ?? "";
    return label.length > 10 ? `${label.slice(0, 10)}…` : label;
  });

  return (
    <div>
      <div className="relative" style={{ height }}>
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          {[0, 25, 50, 75].map((y) => (
            <line
              key={y}
              x1="0"
              x2="100"
              y1={y}
              y2={y}
              stroke="currentColor"
              strokeOpacity="0.08"
              strokeWidth="0.4"
            />
          ))}
          {series
            .filter((s) => s.fill)
            .map((s) => (
              <path key={`area-${s.key}`} d={toArea(s.points)} fill={s.color} fillOpacity="0.14" />
            ))}
          {series.map((s) => (
            <path
              key={s.key}
              d={toPath(s.points)}
              fill="none"
              stroke={s.color}
              strokeWidth="1.4"
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        <span className="absolute right-0 top-0 text-[10px] text-gh-text-muted tabular-nums">
          {valueFormatter(maxValue)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-gh-text-muted">
        {tickLabels.map((label, index) => (
          <span key={`${tickIndexes[index]}-${label}`}>{label}</span>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {series.map((s) => (
          <span
            key={s.key}
            className="inline-flex items-center gap-1.5 text-[11px] text-gh-text-secondary"
          >
            <span className="inline-block h-0.5 w-4 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
};
