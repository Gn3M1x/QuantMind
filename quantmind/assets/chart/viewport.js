/* Pure viewport geometry, shared by the browser controller and offline Node tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.QuantMindViewport = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const validRange = r => Array.isArray(r) && r.length === 2 &&
    r.every(Number.isFinite) && r[1] > r[0];

  function constrainRange(count, requested) {
    if (!Number.isSafeInteger(count) || count <= 0) return null;
    const left = -.5, right = count - .5;
    if (!validRange(requested)) return [left, right];
    // Move the whole window, never clip its two ends independently. At least one
    // record slot prevents a deeply zoomed fractional gap from becoming empty.
    const width = Math.min(count, Math.max(1, requested[1] - requested[0]));
    const start = Math.max(left, Math.min(right - width, requested[0]));
    return start === right - width ? [right - width, right] : [start, start + width];
  }

  function visibleWindow(count, range) {
    if (!Number.isInteger(count) || count <= 0 || !validRange(range)) return null;
    // Category coordinates are the original row indices, including fractional pans.
    // Only centers (and therefore their wicks) inside the plot are visible records.
    const first = Math.max(0, Math.ceil(range[0] - 1e-9));
    const last = Math.min(count - 1, Math.floor(range[1] + 1e-9));
    if (first > last) return null;
    const middle = (range[0] + range[1]) / 2;
    // Equidistant candles choose the earlier record, consistently across frames.
    const centerIndex = Math.max(first, Math.min(last, Math.ceil(middle - .5)));
    return { first, last, centerIndex };
  }

  function priceRange(observations, range, averages = []) {
    const window = visibleWindow(observations.low.length, range);
    if (!window) return { status: "empty" };
    const { first, last, centerIndex } = window;
    let low = Infinity, high = -Infinity;
    for (let i = first; i <= last; i++) {
      const l = observations.low[i], h = observations.high[i];
      // Production data is already validated in Python. Never silently drop a bad row.
      if (!Number.isFinite(l) || !Number.isFinite(h) || l <= 0 || h < l)
        return { status: "invalid", index: i };
      low = Math.min(low, l); high = Math.max(high, h);
      for (const values of averages) {
        const value = values[i];
        if (value == null) continue; // insufficient indicator history, not a zero
        if (!Number.isFinite(value)) return { status: "invalid", index: i };
        low = Math.min(low, value); high = Math.max(high, value);
      }
    }
    const center = observations.low[centerIndex] +
      (observations.high[centerIndex] - observations.low[centerIndex]) / 2;
    const radius = Math.max(center - low, high - center, Math.abs(center) * .002, 1e-6);
    const yRange = [center - 1.1 * radius, center + 1.1 * radius];
    if (!yRange.every(Number.isFinite)) return { status: "invalid", index: centerIndex };
    return { status: "ok", ...window, center, low, high, radius, range: yRange };
  }

  function panByPixels(range, pixels, width) {
    if (!validRange(range) || !Number.isFinite(pixels) || !Number.isFinite(width) || width <= 0) return null;
    const span = range[1] - range[0];
    const left = range[0] - pixels * span / width;
    return [left, left + span];
  }

  function zoomAt(range, fraction, factor) {
    if (!validRange(range) || !Number.isFinite(factor) || factor <= 0) return null;
    const position = Math.max(0, Math.min(1, fraction));
    const oldSpan = range[1] - range[0];
    const newSpan = Math.max(1, oldSpan * factor);
    const anchor = range[0] + oldSpan * position;
    return [anchor - newSpan * position, anchor + newSpan * (1 - position)];
  }

  return { validRange, constrainRange, visibleWindow, priceRange, panByPixels, zoomAt };
});
