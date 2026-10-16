# Local Plotly chart

`plotly.min.js` is the unchanged Plotly.js **3.7.0** bundle shipped in the pinned
Plotly Python **6.9.0** wheel (`plotly/package_data/plotly.min.js`). Its upstream
MIT license is preserved in `PLOTLY-LICENSE.txt`. No CDN, npm build, or extra runtime
server is needed. If upgrading Plotly, replace this bundle and license deliberately,
check the bundle header, then rerun both the geometry and browser checks.

`index.html` uses the small public Streamlit v1 component message protocol:
componentReady (API 1), render arguments, setFrameHeight. It does not send widget
values or triggers during interactions. Analysis data enters only via JSON render
arguments, never through executable HTML interpolation.

`viewport.js` is the pure, shared geometry module. Tests execute this exact file
with Node's built-in test runner. Category coordinates always refer to original
row indices; it does not create a calendar or fill observations.

`constrainRange(count, requested)` is the shared range gate. The browsable count
is the selected `Analysis.frame` (warm-up history is excluded). Bounds are
`[-0.5, count - 0.5]`; shift the whole window, cap its width at count, and retain
at least one record slot. Empty data returns null. Pointer moves consume each
delta even at a boundary, so reversing does not have to repay overshoot. Wheel,
pinch, modebar zoom, native range events, reset and session restoration use this
same gate before visible-record and price calculations. Plotly minallowed and
maxallowed also guard native scale previews; they are not used to implement pan
by independently truncating endpoints. Main plot and bottom time-scale panning
are owned by the controller.

`controller.js` owns pointer panning and horizontal wheel/pinch gestures. Draws
are serialized, at most about 30 per second, with last-input-wins backpressure and
final calibration. Plotly's relayout events cover native zoom and manual scale
adjustments; internal relayouts are guarded to prevent recursion. Native zoom-box
preview events deliberately do not mutate the committed viewport.

State lives in this iframe's memory/sessionStorage under the analysis query UUID.
UI rerenders preserve it; a new query UUID resets it. Listeners are removed before
rebinding and on pagehide; observers, timers and animation frames are cleaned up.

Primary references:

- https://docs.streamlit.io/develop/concepts/custom-components/components-v1/intro
- https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart
- https://github.com/plotly/plotly.js/blob/v3.7.0/src/plots/cartesian/dragbox.js
