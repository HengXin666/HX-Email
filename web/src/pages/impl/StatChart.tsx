import React, { useMemo, useRef, useState } from "react";

interface ChartPoint {
  label: string;
  value: number;
  /** 悬浮提示中额外展示的明细 (如该刷新轮次的成功/失败计数). */
  detail?: string;
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
  /** 固定纵轴最大值 (如成功率图表固定 100); 缺省按数据最大值自适应. */
  maxValue?: number;
}

/**
 * 轻量 SVG 折线图 (无第三方依赖):
 * - 折线/面积用归一化 viewBox 绘制, 坐标文字用 HTML 避免拉伸变形
 * - 左侧纵坐标刻度 (0 / 中值 / 最大值)
 * - 鼠标悬浮显示横轴标签与各序列取值 (参考线 + 悬浮提示)
 */
export const StatChart: React.FC<StatChartProps> = ({
  series,
  height = 168,
  valueFormatter = (value) => String(value),
  maxValue,
}) => {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const allValues: number[] = useMemo(
    () => series.flatMap((s) => s.points.map((p) => p.value)),
    [series],
  );
  const computedMax: number = Math.max(1, ...allValues);
  const yMax: number = maxValue ?? computedMax;
  const pointCount: number = Math.max(2, ...series.map((s) => s.points.length));
  const yTicks: number[] = [yMax, Math.round(yMax / 2), 0];

  const toPath = (points: ChartPoint[]): string =>
    points
      .map((point, index) => {
        const x: number = pointCount <= 1 ? 0 : (index / (pointCount - 1)) * 100;
        const y: number = 96 - (point.value / yMax) * 88;
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

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>): void => {
    const rect = chartRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return;
    const fraction: number = (e.clientX - rect.left) / rect.width;
    const index: number = Math.min(
      pointCount - 1,
      Math.max(0, Math.round(fraction * (pointCount - 1))),
    );
    setHoverIndex(index);
  };

  const hoveredLabel: string =
    hoverIndex !== null ? (series[0]?.points[hoverIndex]?.label ?? "") : "";
  const hoverX: number = hoverIndex !== null ? (hoverIndex / (pointCount - 1)) * 100 : 0;

  return (
    <div>
      <div className="flex">
        {/* 纵坐标刻度 */}
        <div
          className="flex w-9 shrink-0 flex-col justify-between pr-1 text-right text-[10px] text-gh-text-muted tabular-nums"
          style={{ height }}
        >
          {yTicks.map((tick) => (
            <span key={tick}>{valueFormatter(tick)}</span>
          ))}
        </div>
        {/* 绘图区 */}
        <div
          ref={chartRef}
          className="relative flex-1"
          style={{ height }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-hidden
          >
            {[0, 25, 50, 75, 100].map((y) => (
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
                <path
                  key={`area-${s.key}`}
                  d={toArea(s.points)}
                  fill={s.color}
                  fillOpacity="0.14"
                />
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
            {/* 悬浮参考线 + 数据点 */}
            {hoverIndex !== null && (
              <line
                x1={hoverX}
                x2={hoverX}
                y1="0"
                y2="100"
                stroke="currentColor"
                strokeOpacity="0.35"
                strokeWidth="0.6"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {hoverIndex !== null &&
              series.map((s) => {
                const point = s.points[hoverIndex];
                if (!point) return null;
                const x: number = (hoverIndex / (pointCount - 1)) * 100;
                const y: number = 96 - (point.value / yMax) * 88;
                return (
                  <circle
                    key={s.key}
                    cx={x}
                    cy={y}
                    r="2.6"
                    fill={s.color}
                    stroke="#0d1117"
                    strokeWidth="0.8"
                    vectorEffect="non-scaling-stroke"
                  />
                );
              })}
          </svg>
          {/* 悬浮提示 */}
          {hoverIndex !== null && hoveredLabel && (
            <div
              className="pointer-events-none absolute z-10 rounded-md border border-gh-border bg-gh-canvas-inset px-2 py-1.5 text-[11px] shadow-lg"
              style={{
                left: `${Math.min(88, Math.max(12, hoverX))}%`,
                top: 4,
                transform: "translateX(-50%)",
                maxWidth: 180,
              }}
            >
              <div className="font-medium text-gh-text">{hoveredLabel}</div>
              {(() => {
                const detail = series[0]?.points[hoverIndex]?.detail;
                return detail ? (
                  <div className="mt-0.5 text-gh-text-secondary">{detail}</div>
                ) : null;
              })()}
              {series.map((s) => {
                const point = s.points[hoverIndex];
                if (!point) return null;
                return (
                  <div key={s.key} className="mt-0.5 flex items-center gap-1.5">
                    <span
                      className="inline-block h-2 w-2 rounded-sm"
                      style={{ background: s.color }}
                    />
                    <span className="text-gh-text-secondary">{s.label}</span>
                    <span className="ml-auto pl-2 font-semibold text-gh-text tabular-nums">
                      {valueFormatter(point.value)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      {/* 横轴刻度 */}
      <div className="mt-1 flex items-center justify-between pl-9 text-[10px] text-gh-text-muted">
        {tickIndexes.map((index) => {
          const label: string = series[0]?.points[index]?.label ?? "";
          return (
            <span key={`${index}-${label}`}>
              {label.length > 10 ? `${label.slice(0, 10)}…` : label}
            </span>
          );
        })}
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
