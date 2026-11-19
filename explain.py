# Learn mode: a definition, what it means in this app, how to read it and something to
# try, for every graph, result and input. When the Learn switch is on, short notes
# appear next to each one, and they quote numbers from your current flight.

import math
from dataclasses import dataclass
from html import escape

import streamlit as st


@dataclass
class Ctx:
    # What the explanations need to quote numbers from the current flight
    r: dict
    info: dict
    motor: object
    rocket: object
    env: object
    k: float       # metres to display length unit
    ul: str        # length unit
    us: str        # speed unit
    safe: float    # safe landing speed, m/s

    @property
    def ok(self):
        return self.r["apogee_t"] is not None and self.r["burnout_t"] is not None \
            and self.r["apogee"] >= 1.0


def _chute_speed(c):
    # Speed a parachute-borne rocket settles at, from drag balancing weight
    m = c.rocket.dry_mass + c.motor.total_mass - c.motor.prop_mass
    cda = c.rocket.chute_cd * c.rocket.chute_area
    return math.sqrt(2 * m * c.env.g / (c.env.rho_pad * cda))


def _live(c, fn):
    # Run a live-value function, and stay quiet when the flight cannot supply it
    try:
        return fn(c) if c is not None and c.ok else None
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


# Each entry: tab (short label), term, definition, app (what it is here),
# look (how to read it, or what changes in the graphs), try (an experiment),
# live (optional function of Ctx returning a sentence about your flight)
E = {}


def add(key, tab, term, definition, app, look, try_, live=None):
    E[key] = dict(tab=tab, term=term, definition=definition, app=app, look=look,
                  try_=try_, live=live)


# ------------------------------------------------------------------ graphs
add("g_altitude", "Altitude graph", "Altitude",
    "Height above the pad over time. Peak is apogee; the flat descent is under the parachute.",
    "", "", "",
    lambda c: f"Peak {c.r['apogee'] * c.k:.0f} {c.ul} at {c.r['apogee_t']:.1f} s, lands at {c.r['flight_time']:.1f} s.")

add("g_velocity", "Velocity graph", "Velocity",
    "Vertical speed — positive up, negative down. Crosses zero at apogee. Flattens to terminal speed under the chute.",
    "", "", "",
    lambda c: f"Peak {c.r['max_speed'] * c.k:.0f} {c.us}; descent settles near {_chute_speed(c) * c.k:.1f} {c.us}.")

add("g_accel", "Acceleration graph", "Acceleration",
    "Rocket's net acceleration in g. Spikes at ignition (peak load), goes slightly negative at burnout, spikes again when the chute opens.",
    "", "", "",
    lambda c: f"Peak {c.r['max_acc_g']:.1f} g.")

add("g_thrust", "Thrust curve", "Thrust curve",
    "Motor force in newtons over time, from real data. Area under the curve = total impulse = motor class.",
    "", "", "",
    lambda c: f"Peak {c.info['peak_thrust']:.1f} N · {c.info['impulse']:.1f} N·s over {c.motor.burn_time:.2f} s.")

add("events", "Flight events", "Flight events",
    "Dashed lines mark burnout, apogee, ejection and landing. Ideal: ejection sits just after apogee.",
    "", "", "",
    lambda c: f"Burnout {c.r['burnout_t']:.2f} s · apogee {c.r['apogee_t']:.2f} s · ejection {c.r['chute_t']:.2f} s.")

add("g_compare", "Compare motors", "Compare motors",
    "Same rocket, every motor. Higher curve = more impulse. Check Delay vs Ideal delay — a big gap means wrong timing.",
    "", "", "")

add("g_sweep", "Sweeps", "Sweeps",
    "One result vs one input, everything else fixed. Steep line = high sensitivity. Gap = rocket can't lift off there.",
    "", "", "")

add("g_validate", "Validation", "Validation",
    "This sim overlaid on an OpenRocket export. Curves on top of each other = good agreement.",
    "", "", "",
    lambda c: f"Your apogee {c.r['apogee'] * c.k:.1f} {c.ul}.")

# ----------------------------------------------------------------- results
add("apogee", "Apogee", "Apogee",
    "Highest point of the flight — where vertical speed reaches zero.",
    "", "", "",
    lambda c: f"{c.r['apogee'] * c.k:.1f} {c.ul} at {c.r['apogee_t']:.2f} s.")

add("max_speed", "Max speed", "Max speed",
    "Fastest point of the flight, reached at burnout. Speed of sound is 343 m/s (Mach 1).",
    "", "", "",
    lambda c: f"{c.r['max_speed'] * c.k:.0f} {c.us} — Mach {c.r['max_speed'] / 343:.2f}.")

add("max_accel", "Max acceleration", "Max accel",
    "Largest g-load — usually at ignition. Everything on the rocket must survive this force.",
    "", "", "",
    lambda c: f"{c.r['max_acc_g']:.1f} g ({c.r['max_acc_g'] * 9.81:.0f} m/s²).")

add("twr", "Thrust-to-weight", "Thrust / weight",
    "Peak thrust ÷ liftoff weight. Must be above 1 to fly; 5+ recommended for rod stability.",
    "", "", "",
    lambda c: f"{c.info['tw']:.1f}:1 from {c.info['peak_thrust']:.1f} N peak thrust.")

add("burnout", "Burnout", "Burnout",
    "When the motor stops. Speed is at its peak here; the rocket coasts from this point on.",
    "", "", "",
    lambda c: f"{c.r['burnout_t']:.2f} s.")

add("impulse", "Total impulse", "Total impulse",
    "Thrust × time, summed. Sets the motor letter class — each letter is twice the impulse of the last.",
    "", "", "",
    lambda c: f"{c.info['impulse']:.1f} N·s → class {c.info['class']}.")

add("parachute_out", "Parachute out", "Chute deploy",
    "When the ejection charge fires, counted from burnout. Best within ±1 s of apogee.",
    "", "", "",
    lambda c: f"{c.r['chute_t']:.1f} s — {abs(c.info['ejection_offset']):.1f} s "
              f"{'before' if c.info['ejection_offset'] < 0 else 'after'} apogee.")

add("ideal_delay", "Ideal delay", "Ideal delay",
    "The delay that fires the chute exactly at apogee: apogee time − burnout time.",
    "", "", "",
    lambda c: f"~{c.info['ideal_delay']:.1f} s (your delay: {c.motor.delay:.1f} s).")

add("landing_speed", "Landing speed", "Landing speed",
    "Speed at touchdown. Under ~6 m/s is safe for most model rockets.",
    "", "", "",
    lambda c: (f"{c.info['landing_speed'] * c.k:.1f} {c.us} vs limit {c.safe * c.k:.1f} {c.us}.")
              if c.info["landed"] else None)

add("flight_time", "Flight time", "Flight time",
    "Ignition to touchdown. Mostly parachute descent — bigger chute = longer flight.",
    "", "", "",
    lambda c: f"{c.r['flight_time']:.1f} s.")

add("max_q", "Max dynamic pressure", "Max Q",
    "½ρv² — the peak aerodynamic load on the airframe and fins. Highest risk of flutter here.",
    "", "", "",
    lambda c: f"{c.info['max_q'] / 1000:.2f} kPa.")

# ------------------------------------------------------------------ inputs
add("i_motor", "Motor", "Motor",
    "Defines thrust curve, mass and ejection delay. Bigger letter = more impulse = higher flight.",
    "", "", "")

add("i_delay", "Ejection delay", "Ejection delay",
    "Seconds after burnout until the parachute fires. Match it to the ideal delay shown above.",
    "", "", "")

add("i_loaded", "Loaded mass", "Loaded mass",
    "Full motor weight before firing. Propellant burns off during the burn, reducing mass.",
    "", "", "")

add("i_prop", "Propellant mass", "Propellant mass",
    "Mass burned away during the burn. The rocket gets lighter as it climbs — slightly boosting late acceleration.",
    "", "", "")

add("i_dry", "Dry mass", "Dry mass",
    "Rocket without the motor. Strongest single input — heavier = lower apogee and faster descent.",
    "", "", "")

add("i_diameter", "Body diameter", "Diameter",
    "Frontal area = π·d²/4. Wider body = more drag. Drag scales with area, not diameter.",
    "", "", "",
    lambda c: f"Frontal area {c.rocket.area * 1e4:.2f} cm².")

add("i_cd", "Drag coefficient", "Body Cd",
    "Shape's aerodynamic 'slipperiness'. Typical model rockets: 0.4–0.8. Lower = higher apogee.",
    "", "", "",
    lambda c: f"Cd {c.rocket.cd:.2f}.")

add("i_chute_d", "Parachute diameter", "Chute size",
    "Bigger chute = more drag = slower descent. Increase until landing speed is safe.",
    "", "", "",
    lambda c: f"Descent ~{_chute_speed(c) * c.k:.1f} {c.us}.")

add("i_chute_cd", "Parachute Cd", "Chute Cd",
    "How well the chute catches air. 0.7–1.5 typical. Higher = slower descent, same as larger chute.",
    "", "", "")

add("i_elevation", "Launch elevation", "Elevation",
    "Higher pad = thinner air = less drag = higher apogee, but also faster parachute descent.",
    "", "", "",
    lambda c: f"Air density at pad: {c.env.rho_pad:.3f} kg/m³.")

add("i_rho", "Air density", "Sea-level ρ",
    "Standard air ~1.225 kg/m³. Hot day = thinner air = slightly higher apogee, faster landing.",
    "", "", "")

add("i_scale", "Scale height", "Scale height",
    "How fast air thins with altitude. At one scale height up, density is 37% of pad density.",
    "", "", "")

add("i_gravity", "Gravity", "Gravity",
    "Earth: 9.81 m/s². Moon: 1.62 · Mars: 3.71. Lower g = much higher apogee.",
    "", "", "")

add("i_safe", "Safe landing speed", "Safe speed",
    "Your landing-speed limit. Only changes the warning colour — not the physics.",
    "", "", "")

add("i_dt", "Time step", "Time step",
    "Simulation slice size. 0.01 s is accurate for model rockets; halving it shouldn't change results.",
    "", "", "")

add("i_maxt", "Max flight time", "Max flight time",
    "Simulation safety cut-off. Raise it if you get a 'still airborne' warning.",
    "", "", "")

# ---------------------------------------------------------------- concepts
add("c_drag", "Drag", "Drag",
    "D = ½ρv²·Cd·A. Speed is squared — doubling speed quadruples drag. Switches to chute Cd after ejection.",
    "", "", "",
    lambda c: f"Body CdA {c.rocket.cd * c.rocket.area * 1e4:.2f} cm² · chute CdA {c.rocket.chute_cd * c.rocket.chute_area * 1e4:.0f} cm².")

add("c_terminal", "Terminal velocity", "Terminal velocity",
    "Speed where drag = weight: v = √(2mg/ρCdA). This is your descent rate under the chute.",
    "", "", "",
    lambda c: f"~{_chute_speed(c) * c.k:.1f} {c.us} for your rocket.")

add("c_atmo", "Atmosphere", "Atmosphere",
    "Density = ρ₀ · e^(−h/H). Simple exponential — close to real for low-altitude flights.",
    "", "", "")

add("c_newton", "Newton's law", "Equation of motion",
    "m·a = Thrust − m·g ∓ Drag. Applied at every time step — every curve on every graph comes from this.",
    "", "", "")

add("c_phases", "Flight phases", "Flight phases",
    "Boost → coast → descent → landed. Transitions at burnout, apogee and touchdown.",
    "", "", "")

add("c_euler", "Numerical integration", "Integration",
    "Each step: compute force → update speed → update height. 0.01 s steps give < 0.05 m error.",
    "", "", "")

add("c_limits", "Model limits", "Limits",
    "No wind, no launch angle, constant Cd, no transonic drag rise, instant chute deployment.",
    "", "", "")


_LABELS = {"definition": "What", "app": "Here", "look": "Graph", "try_": "Try"}


def note_html(key, c, parts=("definition",)):
    # A compact note for one item, shown inline when Learn is switched on.
    # Renders as: TERM — one tight sentence. Live value on a second line if available.
    e = E[key]
    # Build a single blended sentence from requested parts
    sentences = [e[p].rstrip(". ") for p in parts if e.get(p)]
    text = ". ".join(sentences) + "."
    line = _live(c, e["live"]) if e.get("live") else None
    live_html = (f'<p class="rf-you"><em>now</em>{escape(line)}</p>' if line else "")
    return (f'<div class="rf-note">'
            f'<span class="rf-nt">{escape(e["term"])}</span>'
            f'<p>{escape(text)}</p>'
            f'{live_html}</div>')


def note(keys, c, parts=("definition",)):
    # Show notes for several items, one after another
    for key in keys:
        if key in E:
            st.html(note_html(key, c, parts))
