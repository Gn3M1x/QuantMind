/* Local-only interaction controller. No widget values are sent on pointer/wheel events. */
(function () {
  "use strict";
  const V = window.QuantMindViewport, gd = document.getElementById("chart");
  const toggle = document.getElementById("auto-follow"), reset = document.getElementById("reset-view");
  const status = document.getElementById("view-status");
  let payload, state, initialRange, storageKey, drag = null, internal = 0, rendering = false;
  let dirty = false, finalRequested = false, busy = false, frame = 0, lastPaint = 0, wheelEnd = 0;
  let renderQueue = Promise.resolve(), disposed = false, resizeFrame = 0;
  let nativeBoxZoom = false;
  const abort = new AbortController();
  const post = (type, values = {}) => parent.postMessage({ isStreamlitMessage: true, type, ...values }, "*");
  const axes = () => Object.keys(gd.layout || {}).filter(k => /^xaxis\d*$/.test(k));
  const equal = (a, b) => V.validRange(a) && V.validRange(b) &&
    a.every((v, i) => Math.abs(v - b[i]) <= Math.max(1, Math.abs(v)) * 1e-11);
  // Every input and restored view passes this same gate before price geometry.
  // dates contains only Analysis.frame, never the indicator warm-up history.
  function setRange(requested) {
    state.xRange = V.constrainRange(payload.dates.length, requested);
  }

  function save() {
    if (!state || !storageKey) return;
    try { sessionStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* private browsing: in-memory state still works */ }
  }
  function restored(key) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(key));
      return saved && V.validRange(saved.xRange) && typeof saved.follow === "boolean" ? saved : null;
    } catch (_) { return null; }
  }
  function height() {
    if (!payload) return;
    post("streamlit:setFrameHeight", { height: payload.figure.layout.height + document.querySelector(".chart-toolbar").offsetHeight + 2 });
  }
  function averages() {
    return (gd.data || []).filter(t => ["MA5", "MA20", "MA60"].includes(t.name) &&
      t.visible !== false && t.visible !== "legendonly").map(t => payload.observations[t.name.toLowerCase()]);
  }
  function updateStatus(calculated) {
    const good = calculated.status === "ok";
    status.dataset.error = String(!good);
    status.textContent = good ? `${state.follow ? "自动跟随" : "手动纵轴"} · 可见 ${calculated.last - calculated.first + 1} 条 · 中心 ${payload.dates[calculated.centerIndex]}` :
      calculated.status === "empty" ? "所选区间没有已加载行情。" : "当前行情存在异常，已暂停价格轴跟随。";
    gd.dataset.autoFollow = String(state.follow);
    gd.dataset.centerIndex = good ? String(calculated.centerIndex) : "";
    gd.dataset.phase = drag ? "dragging" : "settled";
  }

  // A single serial render queue, capped at ~30 frames/s. The newest x range wins.
  // Each draw changes every linked x axis and the main price y axis atomically.
  function requestDraw(final = false) {
    dirty = true; finalRequested ||= final;
    if (!frame && !disposed) frame = requestAnimationFrame(flush);
  }
  async function flush(now) {
    frame = 0;
    if (disposed || !state || rendering) return;
    if (busy || (!finalRequested && now - lastPaint < 32)) {
      frame = requestAnimationFrame(flush); return;
    }
    if (!dirty) return;
    dirty = false;
    const final = finalRequested; finalRequested = false;
    setRange(state.xRange);
    const calculated = V.priceRange(payload.observations, state.xRange, averages());
    if (!state.xRange) { updateStatus(calculated); return; }
    const patch = {};
    for (const axis of axes()) {
      if (!equal(gd.layout[axis].range, state.xRange)) patch[`${axis}.range`] = [...state.xRange];
    }
    if (state.follow && calculated.status === "ok" && !equal(gd.layout.yaxis.range, calculated.range))
      patch["yaxis.range"] = calculated.range;
    if (!state.follow && V.validRange(state.manualY) && !equal(gd.layout.yaxis.range, state.manualY))
      patch["yaxis.range"] = [...state.manualY];
    if (gd.layout.yaxis.fixedrange !== state.follow) patch["yaxis.fixedrange"] = state.follow;
    updateStatus(calculated);
    if (Object.keys(patch).length) {
      busy = true; internal++;
      try { await Plotly.relayout(gd, patch); }
      catch (error) { status.textContent = "图表更新失败，请恢复视图。"; console.error(error); }
      finally { internal--; busy = false; lastPaint = performance.now(); }
    }
    if (!state.follow && V.validRange(gd.layout.yaxis.range)) state.manualY = [...gd.layout.yaxis.range];
    if (final && !dirty) save();
    if (dirty) requestDraw(final);
  }

  function eventRange(event) {
    for (const axis of axes()) {
      if (V.validRange(event[`${axis}.range`])) return [...event[`${axis}.range`]];
      const old = state.xRange;
      const pair = [event[`${axis}.range[0]`] ?? old[0], event[`${axis}.range[1]`] ?? old[1]];
      if ((`${axis}.range[0]` in event || `${axis}.range[1]` in event) && V.validRange(pair)) return pair;
    }
    return null;
  }
  function onRange(event, final) {
    if (internal || rendering || !state) return;
    // A zoom box is a preview, not a committed viewport. Re-entering relayout
    // here would compound the native rectangle transform on every mousemove.
    if (!final && nativeBoxZoom) return;
    if (final) nativeBoxZoom = false;
    if (axes().some(axis => event[`${axis}.autorange`] === true)) { resetView(); return; }
    const range = eventRange(event);
    if (range) setRange(range);
    if (!state.follow && ("yaxis.range" in event || "yaxis.range[0]" in event || "yaxis.range[1]" in event))
      state.manualY = [...gd.layout.yaxis.range];
    if (range || state.follow) requestDraw(final);
    else if (final) save();
  }
  const onRelayout = event => onRange(event, true);
  const onRelayouting = event => onRange(event, false);
  const onRestyle = () => { if (!internal && !rendering) requestDraw(true); };
  function unbindPlot() {
    if (!gd.removeListener) return;
    gd.removeListener("plotly_relayout", onRelayout);
    gd.removeListener("plotly_relayouting", onRelayouting);
    gd.removeListener("plotly_restyle", onRestyle);
  }
  function bindPlot() {
    unbindPlot();
    gd.on("plotly_relayout", onRelayout);
    gd.on("plotly_relayouting", onRelayouting);
    gd.on("plotly_restyle", onRestyle);
  }

  function resetView() {
    if (!state || !initialRange) return;
    setRange(initialRange); state.follow = true; state.manualY = null;
    toggle.checked = true; requestDraw(true);
  }
  reset.addEventListener("click", resetView, { signal: abort.signal });
  toggle.addEventListener("change", () => {
    if (!state) return;
    state.follow = toggle.checked;
    state.manualY = [...gd.layout.yaxis.range];
    requestDraw(true);
  }, { signal: abort.signal });

  // Plotly 3.7 emits relayouting, but native pan translates SVG layers during the
  // gesture. Own the default horizontal gesture to update x/y in the same frame;
  // native zoom buttons, box zoom and manual axis drags still use Plotly events.
  gd.addEventListener("pointerdown", event => {
    const axisPan = event.target.closest(".ewdrag");
    if (!V.validRange(state?.xRange) || rendering || event.button !== 0 ||
        !(axisPan || event.target.closest(".nsewdrag"))) return;
    const mode = event.ctrlKey ? "pan" : event.shiftKey ?
      (gd.layout.dragmode === "pan" ? "zoom" : "pan") : gd.layout.dragmode;
    nativeBoxZoom = !axisPan && mode === "zoom";
    if (!axisPan && mode !== "pan") return;
    event.preventDefault(); event.stopPropagation();
    drag = { id: event.pointerId, x: event.clientX };
    gd.setPointerCapture(event.pointerId);
    gd.dataset.phase = "dragging";
  }, { capture: true, signal: abort.signal });
  gd.addEventListener("pointermove", event => {
    if (!drag || event.pointerId !== drag.id) return;
    event.preventDefault(); event.stopPropagation();
    setRange(V.panByPixels(state.xRange, event.clientX - drag.x, gd._fullLayout.xaxis._length));
    // Consume excess motion at the boundary. The very next reverse delta moves
    // immediately, even while the mouse button is still down or after a resize.
    drag.x = event.clientX;
    requestDraw();
  }, { capture: true, signal: abort.signal });
  function endDrag(event) {
    if (!drag || (event.pointerId != null && event.pointerId !== drag.id)) return;
    if (gd.hasPointerCapture(drag.id)) gd.releasePointerCapture(drag.id);
    drag = null; requestDraw(true);
  }
  gd.addEventListener("pointerup", endDrag, { capture: true, signal: abort.signal });
  gd.addEventListener("pointercancel", endDrag, { capture: true, signal: abort.signal });
  gd.addEventListener("lostpointercapture", endDrag, { signal: abort.signal });
  gd.addEventListener("dblclick", event => {
    if (event.target.closest(".nsewdrag")) { event.preventDefault(); resetView(); }
  }, { signal: abort.signal });

  gd.addEventListener("wheel", event => {
    if (!V.validRange(state?.xRange) || rendering || !gd._fullLayout) return;
    const box = gd.getBoundingClientRect(), axis = gd._fullLayout.xaxis;
    const x = event.clientX - box.left;
    const yPixel = event.clientY - box.top, priceAxis = gd._fullLayout.yaxis;
    const units = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? axis._length : 1;
    const dx = event.deltaX * units, dy = event.deltaY * units;
    if (x >= axis._offset && x <= axis._offset + axis._length) {
      if (event.ctrlKey || event.metaKey) {
        const factor = Math.exp(Math.max(-.4, Math.min(.4, dy * .003)));
        setRange(V.zoomAt(state.xRange, (x - axis._offset) / axis._length, factor));
      } else if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 0) {
        setRange(V.panByPixels(state.xRange, -dx, axis._length));
      } else return; // vertical wheel remains normal page scrolling
    } else if (!state.follow && x > axis._offset + axis._length && dy &&
               yPixel >= priceAxis._offset && yPixel <= priceAxis._offset + priceAxis._length) {
      // In manual mode the right price scale can also be zoomed with the wheel.
      const y = gd.layout.yaxis.range, center = (y[0] + y[1]) / 2;
      const radius = (y[1] - y[0]) / 2 * Math.exp(Math.max(-.4, Math.min(.4, dy * .003)));
      state.manualY = [center - radius, center + radius];
    } else return;
    event.preventDefault(); event.stopPropagation();
    requestDraw();
    clearTimeout(wheelEnd); wheelEnd = setTimeout(() => requestDraw(true), 130);
  }, { capture: true, passive: false, signal: abort.signal });

  async function render(next) {
    if (disposed) return;
    rendering = true;
    nativeBoxZoom = false;
    if (drag) endDrag({});
    unbindPlot();
    const queryChanged = !payload || next.queryId !== payload.queryId;
    const rangeChanged = !payload || next.rangeKey !== payload.rangeKey;
    payload = next; initialRange = V.constrainRange(next.dates.length, next.figure.layout.xaxis.range);
    storageKey = `quantmind.chart.${next.queryId}`;
    if (queryChanged) {
      state = restored(storageKey) || { xRange: initialRange, follow: true, manualY: null, rangeKey: next.rangeKey };
    }
    if (rangeChanged && state.rangeKey !== next.rangeKey) {
      setRange(initialRange); state.rangeKey = next.rangeKey;
    }
    setRange(state.xRange);
    toggle.checked = state.follow;
    if (!state.xRange) {
      Plotly.purge(gd); updateStatus({ status: "empty" }); height(); rendering = false; return;
    }
    const figure = structuredClone(next.figure), layout = figure.layout;
    // Responsive Plotly containers use 100% height: give their local host a height.
    gd.style.height = `${layout.height}px`;
    for (const key of Object.keys(layout)) {
      if (/^xaxis\d*$/.test(key)) {
        layout[key].range = [...state.xRange]; layout[key].autorange = false;
        // Native edge-scale gestures/box previews also stay within real records.
        layout[key].minallowed = -.5; layout[key].maxallowed = next.dates.length - .5;
      }
      if (/^yaxis\d*$/.test(key)) layout[key].fixedrange = key === "yaxis" ? state.follow : true;
    }
    layout.uirevision = next.queryId;
    layout.yaxis.autorange = false;
    if (!state.follow && V.validRange(state.manualY)) layout.yaxis.range = [...state.manualY];
    if (state.follow) {
      const names = figure.data.filter(t => ["MA5", "MA20", "MA60"].includes(t.name)).map(t => next.observations[t.name.toLowerCase()]);
      const calculated = V.priceRange(next.observations, state.xRange, names);
      if (calculated.status === "ok") layout.yaxis.range = calculated.range;
    }
    internal++;
    try {
      const zoomButton = (name, title, icon, factor) => ({ name, title, icon, click: () => {
        setRange(V.zoomAt(state.xRange, .5, factor)); requestDraw(true);
      } });
      const config = { ...next.config,
        modeBarButtonsToRemove: [...next.config.modeBarButtonsToRemove, "resetScale2d", "zoomIn2d", "zoomOut2d"],
        modeBarButtonsToAdd: [zoomButton("qmZoomIn", "Zoom in", Plotly.Icons.zoom_plus, .5),
          zoomButton("qmZoomOut", "Zoom out", Plotly.Icons.zoom_minus, 2)] };
      await Plotly.react(gd, figure.data, layout, config);
      updateStatus(V.priceRange(next.observations, state.xRange, averages()));
      bindPlot(); height();
    } finally { internal--; rendering = false; }
    requestDraw(true);
  }
  function onMessage(event) {
    if (event.source !== parent || event.data?.type !== "streamlit:render") return;
    const next = event.data.args?.payload;
    if (!next) return;
    renderQueue = renderQueue.then(() => render(next)).catch(error => {
      status.textContent = "图表载入失败，请重新查询。"; status.dataset.error = "true"; console.error(error);
    });
  }
  window.addEventListener("message", onMessage, { signal: abort.signal });
  const observer = new ResizeObserver(() => {
    height();
    if (gd._fullLayout && !resizeFrame) resizeFrame = requestAnimationFrame(() => {
      resizeFrame = 0; if (!disposed) Plotly.Plots.resize(gd);
    });
  });
  observer.observe(document.body);
  window.addEventListener("pagehide", () => {
    disposed = true; save(); abort.abort(); observer.disconnect();
    clearTimeout(wheelEnd); cancelAnimationFrame(frame); cancelAnimationFrame(resizeFrame);
    unbindPlot(); Plotly.purge(gd);
  }, { once: true });
  post("streamlit:componentReady", { apiVersion: 1 });
})();
