# A slider that reports its value while it is being dragged. st.slider only
# reports when the thumb is released, so the charts could not follow the drag.

import streamlit as st

_HTML = """
<div class="wrap">
  <div class="row"><span class="lab"></span><span class="val"></span></div>
  <input type="range" />
</div>
"""

_CSS = """
.wrap { font-family: var(--st-font); color: var(--st-text-color); padding: 2px 0 8px; }
.row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 7px; }
.lab, .val { font-family: var(--st-code-font); font-size: 12.5px; }
.val { color: var(--st-primary-color); font-weight: 500; }
input[type=range] {
  -webkit-appearance: none; appearance: none; width: 100%; height: 20px; margin: 0;
  background: transparent; cursor: pointer; --pct: 0%;
}
input[type=range]:focus { outline: none; }
input[type=range]::-webkit-slider-runnable-track {
  height: 4px; border-radius: 4px;
  background: linear-gradient(to right, var(--st-primary-color) var(--pct), var(--st-border-color) var(--pct));
}
input[type=range]::-moz-range-track {
  height: 4px; border-radius: 4px;
  background: linear-gradient(to right, var(--st-primary-color) var(--pct), var(--st-border-color) var(--pct));
}
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; width: 16px; height: 16px; margin-top: -6px; border-radius: 50%;
  background: var(--st-primary-color); border: 2px solid var(--st-background-color);
  box-shadow: 0 0 0 1px var(--st-primary-color);
}
input[type=range]::-moz-range-thumb {
  width: 12px; height: 12px; border-radius: 50%; background: var(--st-primary-color);
  border: 2px solid var(--st-background-color); box-shadow: 0 0 0 1px var(--st-primary-color);
}
input[type=range]:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 4px var(--st-border-color); }
"""

_JS = """
const instances = new WeakMap()

export default function (component) {
  const { data, parentElement, setStateValue } = component
  const wrap = parentElement.querySelector(".wrap")
  const input = parentElement.querySelector("input")
  const lab = parentElement.querySelector(".lab")
  const val = parentElement.querySelector(".val")
  if (!wrap || !input) return

  // One update in flight at a time. Streamlit restarts the script whenever a new value
  // arrives, so sending faster than a run takes means no run ever finishes and the page
  // freezes until the drag stops. Instead, send the latest position as soon as Python
  // has drawn the previous one.
  // Range first: a value set before min/max/step would snap to the default 0-100 grid
  lab.textContent = data.label
  wrap.title = data.help || ""
  input.min = data.min
  input.max = data.max
  input.step = data.step

  let inst = instances.get(parentElement)
  if (!inst) {
    // A new range input starts at its midpoint; show Python's value before anything
    // compares against it, or the midpoint would be sent as if the user had moved it.
    // `sent` is what the browser actually holds, after snapping to the step grid.
    input.value = data.value
    inst = { dragging: false, inflight: false, sent: Number(input.value), guard: null }
    instances.set(parentElement, inst)
  }

  const paint = (v) => {
    val.textContent = Number(v).toFixed(data.decimals) + (data.unit ? " " + data.unit : "")
    const pct = ((v - data.min) / (data.max - data.min)) * 100
    input.style.setProperty("--pct", pct + "%")
  }

  const flush = () => {
    if (inst.inflight) return
    const v = Number(input.value)
    if (v === inst.sent) return
    inst.inflight = true
    inst.sent = v
    // Safety net: if no redraw comes back (for example the value did not change on the
    // Python side), allow the next send anyway
    clearTimeout(inst.guard)
    inst.guard = setTimeout(() => { inst.inflight = false; flush() }, 400)
    setStateValue("value", v)
  }

  // This function runs again after each rerun. If it carries the value we sent, that
  // update is finished: send whatever the thumb has moved to since.
  if (inst.inflight && Number(data.value) === inst.sent) {
    inst.inflight = false
    clearTimeout(inst.guard)
  }
  const pending = Number(input.value) !== inst.sent
  // Take the value from Python (for example after Reset) only when the user is not
  // dragging and has nothing unsent; otherwise the thumb would jump back
  if (!inst.dragging && !inst.inflight && !pending && Number(input.value) !== Number(data.value)) {
    input.value = data.value
    inst.sent = Number(data.value)
  }
  paint(Number(input.value))
  if (pending) flush()

  input.oninput = () => {
    inst.dragging = true
    paint(Number(input.value))
    flush()
  }
  input.onchange = () => {
    inst.dragging = false
    flush()
  }

  return () => clearTimeout(inst.guard)
}
"""

_SLIDER = st.components.v2.component("rocket_live_slider", html=_HTML, css=_CSS, js=_JS)


class LiveSliders:
    """Sliders that rerun the app continuously while they are dragged.

    add() reserves the slider's place on the page and returns its value straight
    away, but the slider itself is only drawn by mount_all(), which the app calls at
    the very end of the script. A slider asks for its next update when it is drawn,
    so drawing it last means each update waits until the charts and banner have been
    sent. Drawn first, it would restart the script before the charts were reached,
    and the page would only catch up when the drag paused.

    Reset a slider with st.session_state[key]["value"] = v before the script runs.
    """

    def __init__(self):
        self._queue = []

    def add(self, label, min_value, max_value, value, step, *, key, decimals=1,
            unit="", help=None):
        # Rounded so float noise (24.799999...) matches the browser's step grid exactly
        value = round(float(value), 6)
        current = round(float(st.session_state.get(key, {}).get("value", value)), 6)
        self._queue.append((st.container(), key, value, {
            "label": label, "min": min_value, "max": max_value, "step": step,
            "value": current, "decimals": decimals, "unit": unit, "help": help}))
        return current

    def mount_all(self):
        # Call once per run, after everything else (and before any st.stop())
        for slot, key, default, data in self._queue:
            with slot:
                _SLIDER(key=key, data=data, default={"value": default},
                        on_value_change=lambda: None)
        self._queue = []
