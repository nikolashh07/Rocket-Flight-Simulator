# Interactive Streamlit front end for the rocket flight simulator.
# Run with: streamlit run app.py  (or just `python main.py`)

import io
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
import streamlit as st

import explain
import style
import validation_guide
from live_slider import LiveSliders
from main import (ALPHA_III, B6, C6, D12, DATA_DIR, G, RHO, SCALE_HEIGHT,
                  Motor, Rocket, air_density, parse_eng, simulate)

st.set_page_config(page_title="Rocket flight simulator",
                   page_icon=":material/rocket_launch:", layout="wide")

st.html(style.css(st.context.theme.type == "dark"))

BUILTIN_MOTORS = {m.name: m for m in (B6, C6, D12)}
M_TO_FT = 3.28084
UNITS = {"Metric": (1.0, "m", "m/s"), "Imperial": (M_TO_FT, "ft", "ft/s")}
EVENT_ICONS = {"Liftoff": ":material/north:", "Burnout": ":material/local_fire_department:",
               "Apogee": ":material/flag:", "Ejection": ":material/paragliding:",
               "Landing": ":material/south:"}


@dataclass
class Env:
    # Everything outside the rocket and motor that the simulation depends on
    g: float
    rho_sea: float      # kg/m^3 at sea level
    elevation: float    # m, launch site above sea level
    scale_height: float  # m
    dt: float           # s
    max_time: float     # s

    @property
    def rho_pad(self):
        # Air density at the launch pad
        return self.rho_sea * np.exp(-self.elevation / self.scale_height)


# Simulation (cached so sliders, sweeps and comparisons stay fast)
@st.cache_data(show_spinner=False, max_entries=1024)
def _run(times, thrusts, name, total_mass, prop_mass, delay, dry_mass, diameter,
         cd, chute_d, chute_cd, g, rho_pad, scale_height, dt, max_time):
    motor = Motor(name, list(times), list(thrusts), total_mass, prop_mass, delay)
    rocket = Rocket(dry_mass, diameter, cd, chute_d, chute_cd)
    return simulate(motor, rocket, dt, max_time, g, rho_pad, scale_height)


def fly(motor, rocket, env):
    return _run(tuple(motor.times), tuple(motor.thrusts), motor.name,
                motor.total_mass, motor.prop_mass, motor.delay, rocket.dry_mass,
                rocket.diameter, rocket.cd, rocket.chute_diameter, rocket.chute_cd,
                env.g, env.rho_pad, env.scale_height, env.dt, env.max_time)


def launched(r):
    # A real flight burns out, then climbs at least a metre before apogee
    return r["apogee_t"] is not None and r["burnout_t"] is not None and r["apogee"] >= 1.0


def landing_speed(r):
    # Speed on the last step before touchdown (nan if the rocket never landed)
    if launched(r) and len(r["t"]) > 2 and r["alt"][-1] == 0.0:
        return float(abs(r["vel"][-2]))
    return float("nan")


def total_impulse(motor):
    t, f = np.array(motor.times), np.array(motor.thrusts)
    return float(np.sum(np.diff(t) * (f[1:] + f[:-1]) / 2))


def impulse_class(impulse):
    # NAR/Tripoli letter classes double in total impulse (A: 1.26 to 2.5 N·s)
    if impulse <= 1.25:
        return "< A"
    return "ABCDEFGHIJKLMNOPQRS"[min(int(np.ceil(np.log2(impulse / 1.25))), 18) - 1]


def analyze(r, motor, rocket, env):
    # Extra numbers that are useful to a rocketeer but not part of the sim output
    t, alt, vel = r["t"], r["alt"], r["vel"]
    out = {"landed": not np.isnan(landing_speed(r)),
           "landing_speed": landing_speed(r),
           "impulse": total_impulse(motor),
           "peak_thrust": max(motor.thrusts)}
    out["class"] = impulse_class(out["impulse"])
    out["tw"] = out["peak_thrust"] / ((rocket.dry_mass + motor.total_mass) * env.g)
    out["max_q"] = float(np.max(0.5 * air_density(alt, env.rho_pad, env.scale_height) * vel ** 2))
    if launched(r):
        out["ideal_delay"] = r["apogee_t"] - r["burnout_t"]
        out["ejection_offset"] = r["chute_t"] - r["apogee_t"]
        out["deployed"] = r["chute_t"] <= t[-1]
        out["ejection_speed"] = (abs(float(np.interp(r["chute_t"], t, vel)))
                                 if out["deployed"] else float("nan"))
        liftoff = t[np.argmax(vel > 0)]
        out["events"] = [("Liftoff", liftoff), ("Burnout", r["burnout_t"]),
                         ("Apogee", r["apogee_t"])]
        if out["deployed"]:
            out["events"].append(("Ejection", r["chute_t"]))
        if out["landed"]:
            out["events"].append(("Landing", t[-1]))
    return out


def flight_frame(r, motor, rocket, k_len):
    # Time series in display units, ready to chart
    t = r["t"]
    frac = np.clip(t / motor.burn_time, 0, 1)
    return pd.DataFrame({
        "t": t, "alt": r["alt"] * k_len, "vel": r["vel"] * k_len,
        "acc": r["acc"] / G,
        "thrust": np.interp(t, motor.times, motor.thrusts, right=0.0),
        "mass": (rocket.dry_mass + motor.total_mass - motor.prop_mass * frac) * 1000,
    })


# Charts
def _thin(df, y, n=1200):
    # Cut a long series to about n points for fast redraws while a slider moves.
    # Each bucket keeps its lowest and highest point, so sharp peaks (thrust spike,
    # burnout, parachute snap) survive; plain every-nth sampling would drop them.
    if len(df) <= n:
        return df
    vals = df[y].to_numpy()
    edges = np.linspace(0, len(df), n // 2 + 1).astype(int)
    keep = [0, len(df) - 1]
    for a, b in zip(edges[:-1], edges[1:]):
        if b > a:
            seg = vals[a:b]
            keep += [a + int(np.argmin(seg)), a + int(np.argmax(seg))]
    return df.iloc[np.unique(keep)]


def _axes(x_name, y_name):
    return {
        # No tweening between updates: while a slider is dragged the charts get a new
        # flight several times a second, and half-finished animations look choppy
        "animation": False,
        "grid": {"left": 6, "right": 24, "top": 22, "bottom": 6},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "value", "name": x_name, "nameLocation": "middle",
                  "nameGap": 28, "scale": True, "splitLine": {"lineStyle": {"opacity": 0.22, "type": "dashed"}}},
        "yAxis": {"type": "value", "name": y_name, "nameLocation": "middle",
                  "nameGap": 46, "scale": True, "splitLine": {"lineStyle": {"opacity": 0.22, "type": "dashed"}}},
    }


# One colour per event marker, readable on both the light and the dark theme
EVENT_COLORS = {"Burnout": "#d9822b", "Ejection": "#2a9d8f", "Apogee": "#7c5ce0",
                "Landing": "#8d887f", "Current": "#d9822b"}


def event_text(name, value, unit):
    return f"{name} · {value:.2f} {unit}".strip() if unit == "s" else f"{name} · {value:g} {unit}".strip()


def _marks(events, unit="s"):
    # Dashed vertical lines for flight events. Each has its own colour, named in the
    # key above the chart. Labels only appear on hover, because the early events sit
    # too close together for permanent labels to fit.
    data = []
    for n, x in events:
        color = EVENT_COLORS.get(n, "#8d887f")
        data.append({
            "name": n, "xAxis": float(x),
            "lineStyle": {"color": color},
            "label": {"show": False, "formatter": n, "color": color},
            "emphasis": {"label": {"show": True, "formatter": event_text(n, x, unit),
                                   "color": color, "fontWeight": "bold"},
                         "lineStyle": {"width": 2.5}},
        })
    return {"silent": False, "symbol": "none",
            "lineStyle": {"type": "dashed", "width": 1.4},
            "label": {"position": "end", "rotate": 0, "distance": 6},
            "data": data}


def line_chart(df, x, y, x_name, y_name, fmt, events=(), area=False, height=290,
               key=None, event_unit="s"):
    # Gradient fill colours: top = accent blue, bottom = transparent
    grad_color_top = "rgba(80,130,255,0.22)"
    grad_color_bot = "rgba(20,50,160,0.0)"
    series = {"type": "line", "showSymbol": False, "encode": {"x": x, "y": y},
              "lineStyle": {"width": 2.8},
              "tooltip": {"valueFormatter": fmt},
              "areaStyle": {
                  "color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                            "colorStops": [{"offset": 0, "color": grad_color_top},
                                           {"offset": 1, "color": grad_color_bot}]},
                  "opacity": 1
              }}
    if events:
        events = sorted(events, key=lambda e: e[1])
        st.html(style.event_key([(n, event_text("", v, event_unit).lstrip(" ·"),
                                  EVENT_COLORS.get(n, "#8d887f")) for n, v in events]))
        series["markLine"] = _marks(events, event_unit)
    spec = {**_axes(x_name, y_name), "dataset": {"source": _thin(df[[x, y]], y)},
            "series": [series]}
    if x == "t":
        spec["xAxis"]["min"] = 0
    st.echarts_chart(spec, height=height, key=key,
                     alt=f"{y_name} against {x_name.lower()}")


def multi_chart(named_frames, x, y, x_name, y_name, fmt, height=330, markers=(),
                key=None):
    spec = {**_axes(x_name, y_name),
            "legend": {"top": 0, "type": "scroll"},
            "dataset": [{"source": _thin(df[[x, y]], y)} for _, df in named_frames],
            "series": [{"type": "line", "name": name, "datasetIndex": i,
                        "showSymbol": len(df) < 60, "encode": {"x": x, "y": y},
                        "lineStyle": {"width": 2.2},
                        "tooltip": {"valueFormatter": fmt}}
                       for i, (name, df) in enumerate(named_frames)]}
    spec["grid"]["top"] = 40
    if markers:
        spec["series"][0]["markLine"] = _marks(markers)
    st.echarts_chart(spec, height=height, key=key,
                     alt=f"{y_name} compared for {', '.join(n for n, _ in named_frames)}")


def header_delay(text, default=5.0):
    # First numeric delay listed in a .eng header (for example "3-5-7" gives 3)
    for line in text.splitlines():
        parts = line.split()
        if parts and not line.startswith(";"):
            for token in parts[3].split("-"):
                try:
                    return float(token)
                except ValueError:
                    pass
            break
    return default


DEFAULTS = {
    "in_units": "Metric", "in_motor": C6.name,
    "in_dry": ALPHA_III.dry_mass * 1000, "in_diam": ALPHA_III.diameter * 1000,
    "in_cd": ALPHA_III.cd, "in_chute_d": ALPHA_III.chute_diameter * 100,
    "in_chute_cd": ALPHA_III.chute_cd, "in_elev": 0.0, "in_rho": RHO,
    "in_scale": float(SCALE_HEIGHT), "in_g": G, "in_safe": 6.0, "in_dt": 0.01,
    "in_maxt": 300,
}
LIVE_KEYS = {"in_dry", "in_diam", "in_cd", "in_chute_d", "in_chute_cd", "in_elev",
             "in_scale", "in_safe"}


def _put(key, value):
    # Set a widget that is already on the page back to its starting value
    if key not in st.session_state:
        return
    if key in LIVE_KEYS or key.startswith("in_delay_"):
        st.session_state[key]["value"] = value
    else:
        st.session_state[key] = value


def reset_inputs():
    # Runs before the script, so every slider and field really returns to its default
    for key, value in DEFAULTS.items():
        _put(key, value)
    for name, d in st.session_state.get("_motor_defaults", {}).items():
        _put(f"in_delay_{name}", d["delay"])
        _put(f"in_total_{name}", d["total"])
        _put(f"in_prop_{name}", d["prop"])


# Sidebar: every value that is useful to change
live = LiveSliders()  # drawn at the end of the run, see live_slider.py
slots = {}  # Learn notes for the sidebar inputs, filled once the flight is known


def slot(key):
    slots[key] = st.container()


with st.sidebar:
    st.header("Configure flight", icon=":material/tune:")
    learn = st.toggle(":material/school: Learn", key="learn",
                      help="Show plain-language notes next to the graphs, numbers and inputs.")
    st.button("Reset all inputs", icon=":material/restart_alt:", on_click=reset_inputs,
              width="stretch")
    # Defaults live in session state (not in widget arguments) so Reset can restore them
    for _k in ("in_units", "in_rho", "in_g", "in_dt", "in_maxt"):
        st.session_state.setdefault(_k, DEFAULTS[_k])
    units = st.segmented_control("Display units", list(UNITS), key="in_units") or "Metric"
    k_len, u_len, u_spd = UNITS[units]

    motors = dict(BUILTIN_MOTORS)
    with st.expander("Motor", icon=":material/rocket:", expanded=True):
        files = st.file_uploader("Add a motor (.eng)", type="eng",
                                 accept_multiple_files=True, key="motor_files",
                                 help="RASP .eng files are free to download from thrustcurve.org")
        for f in files:
            try:
                text = f.getvalue().decode("utf-8", errors="replace")
                name = f"{f.name.rsplit('.', 1)[0]} (uploaded)"
                m = parse_eng(text, name, header_delay(text))
                if m.burn_time <= 0 or m.total_mass <= m.prop_mass:
                    raise ValueError("needs a positive burn time and total mass above propellant mass")
                motors[name] = m
            except Exception as e:
                st.error(f"Could not read {f.name}: {e}", icon=":material/error:")

        st.session_state["_motor_defaults"] = {
            n: {"delay": float(m.delay), "total": round(m.total_mass * 1000, 2),
                "prop": round(m.prop_mass * 1000, 2)} for n, m in motors.items()}
        names = list(motors)
        if st.session_state.get("in_motor") not in names:
            st.session_state["in_motor"] = C6.name
        base_name = st.selectbox("Motor", names, key="in_motor")
        slot("i_motor")
        base = motors.get(base_name, C6)
        st.session_state.setdefault(f"in_total_{base.name}", round(base.total_mass * 1000, 2))
        st.session_state.setdefault(f"in_prop_{base.name}", round(base.prop_mass * 1000, 2))
        delay = live.add("Ejection delay after burnout", 0.0, 15.0, float(base.delay),
                         0.5, key=f"in_delay_{base.name}", decimals=1, unit="s",
                         help="The ejection charge fires this long after burnout and deploys the parachute.")
        slot("i_delay")
        c1, c2 = st.columns(2)
        total_g = c1.number_input("Loaded mass (g)", 1.0, 500.0, step=0.5,
                                  key=f"in_total_{base.name}")
        prop_g = c2.number_input("Propellant (g)", 0.1, 500.0, step=0.5,
                                 key=f"in_prop_{base.name}")
        slot("i_loaded")
        slot("i_prop")

    with st.expander("Rocket", icon=":material/arrow_upward:", expanded=True):
        dry_g = live.add("Dry mass, no motor", 10.0, 400.0, DEFAULTS["in_dry"], 0.1,
                         key="in_dry", decimals=1, unit="g")
        slot("i_dry")
        diam_mm = live.add("Body diameter", 10.0, 120.0, DEFAULTS["in_diam"], 0.1,
                           key="in_diam", decimals=1, unit="mm")
        slot("i_diameter")
        cd = live.add("Body drag coefficient", 0.20, 1.50, DEFAULTS["in_cd"], 0.01,
                      key="in_cd", decimals=2)
        slot("i_cd")
        chute_cm = live.add("Parachute diameter", 5.0, 150.0, DEFAULTS["in_chute_d"], 1.0,
                            key="in_chute_d", decimals=0, unit="cm")
        slot("i_chute_d")
        chute_cd = live.add("Parachute drag coefficient", 0.40, 2.20, DEFAULTS["in_chute_cd"],
                            0.05, key="in_chute_cd", decimals=2)
        slot("i_chute_cd")

    with st.expander("Environment", icon=":material/air:"):
        elevation = live.add("Launch site elevation", 0.0, 4000.0, 0.0, 50.0, key="in_elev",
                             decimals=0, unit="m", help="Thinner air at altitude means less drag.")
        slot("i_elevation")
        rho_sea = st.number_input("Sea-level air density (kg/m³)", 0.80, 1.40, step=0.01,
                                  key="in_rho")
        slot("i_rho")
        scale_h = live.add("Atmosphere scale height", 6000.0, 10000.0, float(SCALE_HEIGHT),
                           100.0, key="in_scale", decimals=0, unit="m")
        slot("i_scale")
        g = st.number_input("Gravity (m/s²)", 1.0, 25.0, step=0.01, key="in_g",
                            help="Try 1.62 for the Moon or 3.71 for Mars (the air stays Earth-like).")
        slot("i_gravity")

    with st.expander("Safety and solver", icon=":material/shield:"):
        safe_speed = live.add("Safe landing speed", 2.0, 15.0, 6.0, 0.5, key="in_safe",
                              decimals=1, unit="m/s",
                              help="About 6 m/s (20 ft/s) is a common limit for model rockets.")
        slot("i_safe")
        dt = st.select_slider("Time step (s)", [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001],
                              key="in_dt",
                              help="Smaller is more accurate but slower.")
        slot("i_dt")
        max_time = st.slider("Maximum flight time (s)", 60, 600, step=10, key="in_maxt")

if prop_g >= total_g:
    st.error("Propellant mass must be less than the loaded motor mass.",
             icon=":material/error:")
    live.mount_all()
    st.stop()

motor = replace(base, delay=delay, total_mass=total_g / 1000, prop_mass=prop_g / 1000)
rocket = Rocket(dry_g / 1000, diam_mm / 1000, cd, chute_cm / 100, chute_cd)
env = Env(g, rho_sea, elevation, float(scale_h), dt, float(max_time))

result = fly(motor, rocket, env)
info = analyze(result, motor, rocket, env)
df = flight_frame(result, motor, rocket, k_len)

# Learn mode: notes next to the inputs, numbers and graphs while the switch is on
ctx = explain.Ctx(result, info, motor, rocket, env, k_len, u_len, u_spd, safe_speed)
if learn:
    for _key, _slot in slots.items():
        with _slot:
            explain.note([_key], ctx)


def head(number, text, keys=()):
    # Section label, with Learn notes under it while the switch is on
    st.html(style.eyebrow(number, text))
    if learn:
        explain.note(keys, ctx)


# Header: an editorial hero with the headline numbers over the real flight profile
ok = launched(result)
over_limit = info["landed"] and info["landing_speed"] > safe_speed
if ok:
    stats = [
        ("Apogee", f"{result['apogee'] * k_len:.0f}", u_len, f"at {result['apogee_t']:.1f} s", False),
        ("Max speed", f"{result['max_speed'] * k_len:.0f}", u_spd,
         f"{result['max_speed'] / 343:.2f} Mach", False),
        ("Flight time", f"{result['flight_time']:.1f}", "s",
         f"{result['flight_time'] - result['chute_t']:.0f} s on chute"
         if info["landed"] and info["deployed"] else "no parachute"
         if info["landed"] else "still airborne", False),
        ("Landing speed", f"{info['landing_speed'] * k_len:.1f}" if info["landed"] else "n/a",
         u_spd if info["landed"] else "",
         f"limit {safe_speed * k_len:.1f} {u_spd}", over_limit),
    ]
else:
    stats = [(label, "n/a", "", "cannot fly", True)
             for label in ("Apogee", "Max speed", "Flight time", "Landing speed")]
meta = (f"{motor.name} · {info['class']} class",
        f"{motor.name} motor · {info['impulse']:.1f} N·s impulse · {rocket.dry_mass * 1000:.0f} g dry "
        f"· Cd {rocket.cd:.2f} · {rocket.chute_diameter * 100:.0f} cm parachute"
        + (f" · {elevation * k_len:.0f} {u_len} elevation" if elevation else ""))
hero_notes = [explain.E[k]["definition"] for k in ("apogee", "max_speed", "flight_time", "landing_speed")]
if learn:
    stats = [(*s_[:5], n_) for s_, n_ in zip(stats, hero_notes)]
st.html(style.hero(meta, stats, result, learn))

if not ok:
    st.error(f"Peak thrust is {info['peak_thrust']:.1f} N against a liftoff weight of "
             f"{(rocket.dry_mass + motor.total_mass) * env.g:.2f} N, and the thrust drops "
             "below the weight before burnout. Use a stronger motor or reduce the mass.",
             title="The rocket cannot fly", icon=":material/block:")
    live.mount_all()
    st.stop()

# More numbers — custom cards so the Learn note lives inside the card when Learn is on
def _note(key):
    return explain.E[key]["definition"] if learn else None

chute_val = f"{result['chute_t']:.1f} s" if info["deployed"] else "never"
chute_delta = f"{info['ejection_offset']:+.1f} s vs apogee" if info["deployed"] else "landed first"
with st.grid(4, gap="small"):
    st.html(style.metric_card("Max acceleration", f"{result['max_acc_g']:.1f} g",
                              f"{info['tw']:.1f}:1 thrust to weight", _note("max_accel")))
    st.html(style.metric_card("Burnout", f"{result['burnout_t']:.2f} s",
                              f"{info['impulse']:.1f} N·s total impulse", _note("burnout")))
    st.html(style.metric_card("Parachute out", chute_val, chute_delta, _note("parachute_out")))
    st.html(style.metric_card("Max dynamic pressure", f"{info['max_q'] / 1000:.2f} kPa",
                              f"{info['peak_thrust']:.1f} N peak thrust", _note("max_q")))

# Plain-language checks
if info["landed"] and info["landing_speed"] > safe_speed:
    st.warning(f"The rocket lands at {info['landing_speed'] * k_len:.1f} {u_spd}, above your "
               f"{safe_speed * k_len:.1f} {u_spd} limit. Try a larger parachute or a lighter rocket.",
               title="Hard landing", icon=":material/warning:")
if not info["landed"]:
    st.warning("The flight did not finish before the maximum flight time. Raise it in "
               "Safety and solver.", title="Rocket still airborne", icon=":material/warning:")
if not info["deployed"]:
    st.error(f"The rocket lands at {result['flight_time']:.1f} s, before the parachute "
             f"fires at {result['chute_t']:.1f} s. The ideal delay for this flight is about "
             f"{info['ideal_delay']:.1f} s.",
             title="Parachute never deploys", icon=":material/dangerous:")
elif info["ejection_offset"] < -1.0:
    st.warning(f"The parachute deploys {-info['ejection_offset']:.1f} s before apogee, while the "
               f"rocket is still climbing. A delay near {info['ideal_delay']:.1f} s fits this flight.",
               title="Ejection too early", icon=":material/schedule:")
elif info["ejection_offset"] > 2.0 or (np.isfinite(info["ejection_speed"])
                                        and info["ejection_speed"] > 12):
    st.html(style.alert_banner("red", "⏰",
                               "Ejection too late",
                               f"The parachute deploys {info['ejection_offset']:.1f} s after apogee at "
                               f"{info['ejection_speed'] * k_len:.0f} {u_spd}, which can damage the recovery "
                               f"system. A delay near {info['ideal_delay']:.1f} s deploys at the top of the flight."))
else:
    when = (f"{abs(info['ejection_offset']):.1f} s "
            f"{'before' if info['ejection_offset'] < 0 else 'after'} apogee")
    st.html(style.alert_banner("green", "✓",
                               "Ejection well timed",
                               f"The parachute deploys {when}. The ideal delay for this flight is about "
                               f"{info['ideal_delay']:.1f} s."))

if learn:
    explain.note(["ideal_delay", "landing_speed"], ctx)

# Tabs
TAB_NAMES = [":material/show_chart: Flight", ":material/compare_arrows: Compare motors",
             ":material/tune: Sweeps", ":material/fact_check: Validation",
             ":material/table_chart: Data", ":material/menu_book: Physics"]
t_flight, t_compare, t_sweep, t_valid, t_data, t_phys = st.tabs(
    TAB_NAMES, on_change="rerun", key="tabs")

with t_flight:
    if t_flight.open:
        # Liftoff sits on the y-axis at t = 0, so it is only listed in the events table
        events = [(n, t) for n, t in info["events"] if n != "Liftoff"]
        if learn:
            # Notes for a row of charts sit side by side above it, so the charts stay level
            nl, nr = st.columns(2)
            with nl:
                explain.note(["g_altitude", "events"], ctx)
            with nr:
                explain.note(["g_velocity"], ctx)
        left, right = st.columns(2)
        with left, st.container(border=False):
            head(2, "Altitude")
            line_chart(df, "t", "alt", "Time (s)", f"Altitude ({u_len})", f"%.1f {u_len}",
                       events=events, area=True, key="c_alt")
        with right, st.container(border=False):
            head(3, "Velocity")
            line_chart(df, "t", "vel", "Time (s)", f"Velocity ({u_spd})", f"%.1f {u_spd}",
                       events=events, key="c_vel")
        if learn:
            nl, nr = st.columns(2)
            with nl:
                explain.note(["g_accel"], ctx)
            with nr:
                explain.note(["g_thrust"], ctx)
        left, right = st.columns(2)
        with left, st.container(border=False):
            head(4, "Acceleration")
            line_chart(df, "t", "acc", "Time (s)", "Acceleration (g)", "%.2f g",
                       events=events, key="c_acc")
        with right, st.container(border=False):
            head(5, "Motor thrust")
            line_chart(df[df["t"] <= motor.burn_time * 1.5], "t", "thrust", "Time (s)",
                       "Thrust (N)", "%.1f N", area=True, key="c_thr",
                       events=[e for e in events if e[0] == "Burnout"])  # the only one in range

        head(6, "Flight events", ["c_phases"])
        rows = [{"Event": n, "Time (s)": t,
                 "Altitude": float(np.interp(t, result["t"], result["alt"])) * k_len,
                 "Speed": abs(float(np.interp(t, result["t"], result["vel"]))) * k_len}
                for n, t in info["events"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={
                         "Time (s)": st.column_config.NumberColumn(format="%.2f"),
                         "Altitude": st.column_config.NumberColumn(f"Altitude ({u_len})", format="%.1f"),
                         "Speed": st.column_config.NumberColumn(f"Speed ({u_spd})", format="%.1f")},
                     alt="Times, altitudes and speeds of the main flight events")

with t_compare:
    if t_compare.open:
        st.caption("Every motor flies the same rocket and environment. Your sidebar motor "
                   "settings apply to the selected motor.")
        pick = st.multiselect("Motors", names, default=list(BUILTIN_MOTORS) + [
            n for n in names if n not in BUILTIN_MOTORS], key="cmp_motors",
            persist_state="page")
        what = st.segmented_control("Show", ["Altitude", "Velocity", "Acceleration"],
                                    default="Altitude", key="cmp_what",
                                    persist_state="page") or "Altitude"
        col, label, fmt = {"Altitude": ("alt", f"Altitude ({u_len})", f"%.1f {u_len}"),
                           "Velocity": ("vel", f"Velocity ({u_spd})", f"%.1f {u_spd}"),
                           "Acceleration": ("acc", "Acceleration (g)", "%.2f g")}[what]
        frames, table, thrust_frames = [], [], []
        for n in pick:
            m = motor if n == base.name else motors[n]
            r = fly(m, rocket, env)
            if not launched(r):
                st.warning(f"{n} cannot lift this rocket.", icon=":material/block:")
                continue
            a = analyze(r, m, rocket, env)
            frames.append((n, flight_frame(r, m, rocket, k_len)))
            thrust_frames.append((n, pd.DataFrame({
                "t": m.times, "thrust": m.thrusts})))
            table.append({"Motor": n, "Class": a["class"], "Impulse": a["impulse"],
                          "Peak thrust": a["peak_thrust"], "Burn": m.burn_time,
                          "Delay": m.delay, "Ideal delay": a["ideal_delay"],
                          "Apogee": r["apogee"] * k_len,
                          "Max speed": r["max_speed"] * k_len,
                          "Landing": a["landing_speed"] * k_len,
                          "Flight": r["flight_time"]})
        if frames:
            with st.container(border=False):
                head(1, what, ["g_compare"])
                multi_chart(frames, "t", col, "Time (s)", label, fmt, key="cmp_chart")
            with st.container(border=False):
                head(2, "Thrust curves", ["impulse"])
                multi_chart(thrust_frames, "t", "thrust", "Time (s)", "Thrust (N)", "%.1f N",
                            height=260, key="cmp_thrust")
            st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch",
                         column_config={
                             "Impulse": st.column_config.NumberColumn("Impulse (N·s)", format="%.1f"),
                             "Peak thrust": st.column_config.NumberColumn("Peak (N)", format="%.1f"),
                             "Burn": st.column_config.NumberColumn("Burn (s)", format="%.2f"),
                             "Delay": st.column_config.NumberColumn("Delay (s)", format="%.1f"),
                             "Ideal delay": st.column_config.NumberColumn("Ideal delay (s)", format="%.1f"),
                             "Apogee": st.column_config.NumberColumn(f"Apogee ({u_len})", format="%.0f"),
                             "Max speed": st.column_config.NumberColumn(f"Max speed ({u_spd})", format="%.0f"),
                             "Landing": st.column_config.NumberColumn(f"Landing ({u_spd})", format="%.1f"),
                             "Flight": st.column_config.NumberColumn("Flight (s)", format="%.1f")},
                         alt="Motor comparison table with impulse, apogee and landing speed")
        else:
            st.info("Pick at least one motor to compare.", icon=":material/info:")

SWEEPS = {  # name: (unit, min, max, step, default range)
    "Dry mass": ("g", 10.0, 400.0, 0.5, (30.0, 100.0)),
    "Body drag coefficient": ("", 0.20, 1.50, 0.01, (0.40, 0.90)),
    "Body diameter": ("mm", 10.0, 120.0, 0.5, (15.0, 50.0)),
    "Parachute diameter": ("cm", 5.0, 150.0, 1.0, (10.0, 80.0)),
    "Parachute drag coefficient": ("", 0.40, 2.20, 0.05, (0.50, 1.50)),
    "Ejection delay": ("s", 0.0, 15.0, 0.5, (0.0, 12.0)),
    "Launch site elevation": ("m", 0.0, 4000.0, 50.0, (0.0, 3000.0)),
}
SWEEP_CURRENT = {"Dry mass": dry_g, "Body drag coefficient": cd, "Body diameter": diam_mm,
                 "Parachute diameter": chute_cm, "Parachute drag coefficient": chute_cd,
                 "Ejection delay": delay, "Launch site elevation": float(elevation)}


def sweep_apply(name, v):
    if name == "Dry mass":
        return motor, replace(rocket, dry_mass=v / 1000), env
    if name == "Body drag coefficient":
        return motor, replace(rocket, cd=v), env
    if name == "Body diameter":
        return motor, replace(rocket, diameter=v / 1000), env
    if name == "Parachute diameter":
        return motor, replace(rocket, chute_diameter=v / 100), env
    if name == "Parachute drag coefficient":
        return motor, replace(rocket, chute_cd=v), env
    if name == "Ejection delay":
        return replace(motor, delay=v), rocket, env
    return motor, rocket, replace(env, elevation=v)


with t_sweep:
    if t_sweep.open:
        st.caption("Vary one setting at a time and watch the outcome. Everything else stays "
                   "at the sidebar values.")
        c1, c2, c3 = st.columns([2, 3, 2], vertical_alignment="bottom")
        param = c1.selectbox("Setting to sweep", list(SWEEPS), key="sw_param",
                             persist_state="page")
        unit, lo, hi, step, default = SWEEPS[param]
        lo_hi = c2.slider(f"Range{f' ({unit})' if unit else ''}", lo, hi, default, step,
                          key=f"sw_range_{param}", persist_state="page")
        n_pts = c3.slider("Points", 5, 40, 15, key="sw_n", persist_state="page")
        metric = st.segmented_control(
            "Outcome", ["Apogee", "Max speed", "Landing speed", "Flight time", "Max acceleration"],
            default="Apogee", key="sw_metric", persist_state="page") or "Apogee"
        picked = {"Apogee": (lambda r: r["apogee"] * k_len, f"Apogee ({u_len})", f"%.0f {u_len}"),
                  "Max speed": (lambda r: r["max_speed"] * k_len, f"Max speed ({u_spd})", f"%.0f {u_spd}"),
                  "Landing speed": (lambda r: landing_speed(r) * k_len, f"Landing speed ({u_spd})", f"%.1f {u_spd}"),
                  "Flight time": (lambda r: r["flight_time"], "Flight time (s)", "%.1f s"),
                  "Max acceleration": (lambda r: r["max_acc_g"], "Max acceleration (g)", "%.1f g")}
        pick_fn, y_label, y_fmt = picked[metric]
        xs = np.linspace(lo_hi[0], lo_hi[1], n_pts)
        with st.spinner("Flying the sweep..."):
            ys = []
            for v in xs:
                r = fly(*sweep_apply(param, float(v)))
                ys.append(pick_fn(r) if launched(r) else np.nan)
        sweep_df = pd.DataFrame({"x": xs, "y": ys})
        x_label = f"{param} ({unit})" if unit else param
        with st.container(border=False):
            head(1, f"{metric} against {param.lower()}", ["g_sweep"])
            line_chart(sweep_df, "x", "y", x_label, y_label, y_fmt, key="sw_chart",
                       height=340, events=[("Current", SWEEP_CURRENT[param])]
                       if lo_hi[0] <= SWEEP_CURRENT[param] <= lo_hi[1] else (),
                       event_unit=unit)
        if sweep_df["y"].notna().any():
            i = int(sweep_df["y"].idxmax())
            st.caption(f"Highest {metric.lower()} in this range: {sweep_df['y'][i]:.1f} "
                       f"at {param.lower()} = {sweep_df['x'][i]:.2f}"
                       f"{' ' + unit if unit else ''}. Gaps mean the rocket could not lift off.")

with t_valid:
    if t_valid.open:
        st.caption("Compare the simulation with a flight exported from OpenRocket. The bundled "
                   "reference is an Estes Alpha III on a C6-5 motor with the default settings.")
        with st.expander("How to match OpenRocket exactly", icon=":material/menu_book:",
                         expanded=True):
            validation_guide.render(motor, rocket, env)
        upload = st.file_uploader("Use your own OpenRocket CSV", type="csv", key="ref_upload",
                                  help="Four comma-separated columns: time, altitude, velocity "
                                       "and acceleration, in SI units, with # comment lines.")
        ref, source = None, None
        try:
            if upload is not None:
                ref, source = np.loadtxt(io.StringIO(upload.getvalue().decode()),
                                         delimiter=",", comments="#"), upload.name
            elif (DATA_DIR / "openrocket.csv").exists():
                ref, source = np.loadtxt(DATA_DIR / "openrocket.csv", delimiter=",",
                                         comments="#"), "openrocket.csv"
        except Exception as e:
            st.error(f"Could not read that file: {e}", icon=":material/error:")
        if ref is None or ref.ndim != 2 or ref.shape[1] < 4:
            st.info("Add an OpenRocket CSV to compare against.", icon=":material/info:")
        else:
            t_ref, alt_ref, vel_ref, acc_ref = ref[:, :4].T
            err = np.interp(t_ref, result["t"], result["alt"]) - alt_ref
            with st.grid(4, gap="small"):
                st.metric("Apogee, this sim", f"{result['apogee'] * k_len:.1f} {u_len}",
                          delta=f"{100 * (result['apogee'] / alt_ref.max() - 1):+.1f}% vs OpenRocket",
                          delta_color="off", border=False, height="stretch")
                st.metric("Apogee, OpenRocket", f"{alt_ref.max() * k_len:.1f} {u_len}",
                          border=False, height="stretch")
                st.metric("Altitude error (RMS)", f"{np.sqrt(np.mean(err ** 2)) * k_len:.1f} {u_len}",
                          border=False, height="stretch")
                st.metric("Altitude error (max)", f"{np.abs(err).max() * k_len:.1f} {u_len}",
                          delta=f"flight {result['flight_time']:.1f} s vs {t_ref[-1]:.1f} s",
                          delta_color="off", border=False, height="stretch")
            if source == "openrocket.csv" and (motor.name != C6.name or abs(rocket.cd - ALPHA_III.cd) > 1e-9
                                               or abs(rocket.dry_mass - ALPHA_III.dry_mass) > 1e-9):
                st.caption("Your settings differ from the bundled validation case, so some "
                           "difference is expected. Press Reset all inputs to restore it.")
            what_v = st.segmented_control("Show", ["Altitude", "Velocity", "Acceleration"],
                                          default="Altitude", key="val_what") or "Altitude"
            key_v, ref_v, label_v, fmt_v = {
                "Altitude": ("alt", alt_ref * k_len, f"Altitude ({u_len})", f"%.1f {u_len}"),
                "Velocity": ("vel", vel_ref * k_len, f"Velocity ({u_spd})", f"%.1f {u_spd}"),
                "Acceleration": ("acc", acc_ref / G, "Acceleration (g)", "%.2f g")}[what_v]
            with st.container(border=False):
                head(1, f"{what_v}: this sim and OpenRocket", ["g_validate"])
                multi_chart([("OpenRocket", pd.DataFrame({"t": t_ref, key_v: ref_v})),
                             ("This sim", df[["t", key_v]])],
                            "t", key_v, "Time (s)", label_v, fmt_v, key="val_chart")

with t_data:
    if t_data.open:
        left, right = st.columns([3, 2])
        with left:
            head(1, "Flight data", ["c_euler"])
            export = pd.DataFrame({
                "time_s": result["t"], "altitude_m": result["alt"],
                "velocity_m_s": result["vel"], "acceleration_m_s2": result["acc"],
                "thrust_n": df["thrust"], "mass_g": df["mass"]})
            st.download_button("Download CSV", export.to_csv(index=False),
                               file_name=f"flight_{motor.name}.csv", mime="text/csv",
                               icon=":material/download:")
            st.dataframe(export, hide_index=True, height=420, width="stretch",
                         column_config={c: st.column_config.NumberColumn(format="%.3f")
                                        for c in export.columns},
                         alt="Simulated flight time series in SI units")
        with right:
            head(2, "Motor")
            st.table(pd.DataFrame({
                "Name": motor.name, "Total impulse": f"{info['impulse']:.2f} N·s ({info['class']})",
                "Peak thrust": f"{info['peak_thrust']:.1f} N",
                "Average thrust": f"{info['impulse'] / motor.burn_time:.1f} N",
                "Burn time": f"{motor.burn_time:.2f} s", "Ejection delay": f"{motor.delay:.1f} s",
                "Loaded mass": f"{motor.total_mass * 1000:.1f} g",
                "Propellant mass": f"{motor.prop_mass * 1000:.1f} g",
                "Thrust points": str(len(motor.times)),
            }, index=["Value"]).T)
            head(3, "Rocket and environment")
            st.table(pd.DataFrame({
                "Dry mass": f"{rocket.dry_mass * 1000:.1f} g",
                "Liftoff mass": f"{(rocket.dry_mass + motor.total_mass) * 1000:.1f} g",
                "Body diameter": f"{rocket.diameter * 1000:.1f} mm",
                "Frontal area": f"{rocket.area * 1e4:.2f} cm²",
                "Body Cd": f"{rocket.cd:.2f}",
                "Parachute": f"{rocket.chute_diameter * 100:.0f} cm, Cd {rocket.chute_cd:.2f}",
                "Air density at pad": f"{env.rho_pad:.3f} kg/m³",
                "Gravity": f"{env.g:.2f} m/s²",
                "Time step": f"{env.dt} s",
            }, index=["Value"]).T)

with t_phys:
    if t_phys.open:
        head(1, "How it works", ["c_newton", "c_drag", "c_terminal"])
        st.markdown("The simulator steps through the flight in small time increments. At each "
                    "step it adds up the forces on the rocket and updates its speed and height.")
        st.latex(r"m(t)\,a = T(t) - m(t)\,g \mp \tfrac{1}{2}\,\rho(h)\,v^{2}\,C_d A")
        st.markdown("- **Thrust** $T(t)$ is interpolated from a real thrust curve.\n"
                    "- **Mass** $m(t)$ drops linearly from the loaded motor mass to the empty "
                    "casing over the burn.\n"
                    "- **Drag** always opposes motion. After the ejection delay, $C_d A$ switches "
                    "from the body to the parachute.")
        st.latex(r"\rho(h) = \rho_0\,e^{-h/H}")
        st.markdown("Air thins exponentially with height, with $H$ the scale height. Launching "
                    "from a high site lowers $\\rho_0$ for the whole flight.")
        st.markdown("Integration is semi-implicit Euler: speed updates first, then height uses "
                    "the new speed. The time-step convergence check in `main.py` shows the "
                    "apogee settles as the step shrinks.")
        head(2, "Limits", ["c_limits"])
        st.markdown("- Vertical flight only. There is no wind, weathercocking or launch angle.\n"
                    "- Drag coefficients are constant, so there is no Mach or Reynolds effect.\n"
                    "- Propellant burns off at a steady rate, and the centre of mass is ignored.\n"
                    "- Parachute opening is instant.")
        st.caption("Motor data from thrustcurve.org. Validated against OpenRocket.")

st.html(style.footer())

# Last: draw the live sliders, so their next update waits for everything above
live.mount_all()
