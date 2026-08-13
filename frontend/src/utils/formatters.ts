export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 Bytes";

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

export function formatNumber(num: number, decimals = 2): string {
  if (Math.abs(num) >= 1e6) {
    return (num / 1e6).toFixed(decimals) + "M";
  }
  if (Math.abs(num) >= 1e3) {
    return (num / 1e3).toFixed(decimals) + "K";
  }
  return num.toFixed(decimals);
}

export function formatPValue(pValue: number): string {
  if (pValue < 0.001) {
    return pValue.toExponential(2);
  }
  return pValue.toFixed(3);
}

export function formatPercentage(value: number, decimals = 1): string {
  return (value * 100).toFixed(decimals) + "%";
}

export function truncateString(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + "...";
}

export function snakeToTitle(str: string): string {
  return str
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
