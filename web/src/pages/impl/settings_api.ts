export function maskValue(value: string, show: number = 4): string {
  if (!value) return "";
  if (value.length <= show * 2) return "*".repeat(Math.min(value.length, 8));
  return value.slice(0, show) + "*".repeat(4) + value.slice(-show);
}
