# Look and feel for the Streamlit app: an editorial "paper and ink" style with a
# red accent, film grain, monospace labels and a hero drawn from the real flight.

from html import escape

import numpy as np

PAPER = "#f4f1ea"
NAVY = "#0a1630"


def _grain(rgb, alpha):
    # SVG fractal noise as a data URI, used as a film-grain texture
    r, g, b = rgb
    # Angle brackets are percent-encoded because the HTML sanitizer drops <style>
    # blocks that contain a raw "<svg"
    return ("url(\"data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' "
            "width='240' height='240'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' "
            "baseFrequency='.8' numOctaves='2' stitchTiles='stitch'/%3E"
            f"%3CfeColorMatrix values='0 0 0 0 {r} 0 0 0 0 {g} 0 0 0 0 {b} 0 0 0 {alpha} 0'/%3E"
            "%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")")


_CSS = """
<style>
/* Film grain over the whole page */
.stApp::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:9999;
  background-image:__PAGE_GRAIN__;opacity:__GRAIN_OPACITY__;mix-blend-mode:__BLEND__}

/* Live updates: Streamlit fades elements to ~33% while a rerun is in progress. With a
   slider being dragged that fade never finishes, and on the dark banner it shows the
   light page through as a white glare, so keep everything fully opaque. */
[data-testid="stElementContainer"][data-stale="true"],[data-stale="true"]{opacity:1 !important;
  transition:none !important}

/* Headings: tight and heavy */
.stApp h2,.stApp h3{letter-spacing:-.035em}

/* Mono, uppercase labels like a printed index */
[data-testid="stMetricLabel"] p,[role="tab"] p,[data-testid="stExpander"] summary p,
[data-testid="stSidebar"] h2,.stApp label p{font-family:'DM Mono',ui-monospace,monospace !important}
.stApp label p{font-size:12.5px !important}
[data-testid="stMetricLabel"] p,[role="tab"] p,[data-testid="stExpander"] summary p,
[data-testid="stSidebar"] h2{text-transform:uppercase;letter-spacing:.12em !important;font-size:11.5px !important}
[role="tab"]{padding-left:6px;padding-right:6px;margin-right:10px}
[data-testid="stSidebar"]{border-right:1px solid __RULE__}
[data-testid="stSidebar"]::before{content:"";display:block;height:3px;
  background:linear-gradient(90deg,__ACCENT__,rgba(143,178,255,0));
  margin:-1rem -1rem 1.2rem -1rem}
[data-testid="stMetricValue"]{letter-spacing:-.04em}

/* Eyebrow above each section */
.rf-eyebrow{display:flex;align-items:center;gap:12px;font-family:'DM Mono',ui-monospace,monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:__MUTED__;
  margin:2px 0 10px;padding-bottom:8px;border-bottom:1px solid __RULE__}
.rf-eyebrow b{color:__ACCENT__;font-weight:500}

/* Learn notes (sidebar and chart-section inline notes) */
.rf-note{margin:4px 0 10px;padding:0 0 0 11px;border-left:2px solid __ACCENT__;
  background:__NOTEBG__}
.rf-note p{margin:0 0 3px;font-family:'DM Mono',ui-monospace,monospace;font-size:10px;
  letter-spacing:.06em;line-height:1.6;color:inherit;opacity:.8}
.rf-note em{font-style:normal;font-size:9px;letter-spacing:.14em;text-transform:uppercase;
  color:__ACCENT__;margin-right:5px;opacity:1}
.rf-nt{display:block;font-family:'DM Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.18em;
  text-transform:uppercase;color:__ACCENT__;font-weight:600;margin-bottom:5px;opacity:1}
.rf-note .rf-you em{color:__ACCENT__}
.rf-note .rf-you p{opacity:1;font-weight:500}
[data-testid="stSidebar"] .rf-note{padding-left:9px}

/* Custom metric cards (replace st.metric when Learn is on) */
.rf-card{background:transparent;border-top:1px solid __RULE__;padding:12px 0 10px;
  display:flex;flex-direction:column;gap:2px}
.rf-cl{font-family:'DM Mono',ui-monospace,monospace;font-size:11px;letter-spacing:.13em;
  text-transform:uppercase;color:__MUTED__}
.rf-cv{font-size:clamp(18px,2vw,26px);font-weight:700;letter-spacing:-.04em;
  font-variant-numeric:lining-nums tabular-nums;line-height:1.1;margin:2px 0}
.rf-cd{font-family:'DM Mono',ui-monospace,monospace;font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:__MUTED__;margin-bottom:2px}
.rf-cn{font-family:'DM Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.06em;
  line-height:1.6;color:__MUTED__;margin-top:7px;padding-top:7px;border-top:1px solid __RULE__}

/* Custom alert banners */
.rf-alert{display:flex;align-items:flex-start;gap:12px;padding:11px 16px;border-radius:0;
  margin:8px 0;font-size:13.5px;line-height:1.55;border-left:2px solid currentColor}
.rf-alert .rf-ai{font-size:16px;line-height:1.4;flex-shrink:0;opacity:.7}
.rf-alert .rf-ab{display:flex;flex-direction:column;gap:2px}
.rf-alert .rf-at{font-family:'DM Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.15em;
  text-transform:uppercase;font-weight:600;margin-bottom:3px}
.rf-alert.red{background:rgba(180,30,20,.07);color:inherit;border-color:#b01c14}
.rf-alert.red .rf-at{color:#b01c14}
.rf-alert.green{background:rgba(20,90,40,.07);color:inherit;border-color:#1e6b35}
.rf-alert.green .rf-at{color:#1e6b35}

/* Key for the dashed event lines on a chart */
.rf-key{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 2px;font-family:'DM Mono',ui-monospace,monospace;
  font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:__MUTED__}
.rf-key span{display:inline-flex;align-items:center;gap:7px;white-space:nowrap}
.rf-key i{display:inline-block;width:16px;border-top:2px dashed currentColor}
.rf-key b{font-weight:500}

/* Hero: a full-width band, no box, no grid */
.stApp [data-testid="stHeader"]{background:transparent !important}
.stApp [data-testid="stToolbar"]{display:none}
.rf-hero{position:relative;overflow:hidden;isolation:isolate;background:__NAVY__;color:__PAPER__;
  margin:-3.75rem -5rem 28px -5rem;padding:96px 5rem 40px}
.rf-hero::before{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(70% 160% at 92% -10%,rgba(61,111,224,.7),transparent 58%),
  radial-gradient(55% 110% at 0% 130%,rgba(30,70,180,.28),transparent 65%),
  radial-gradient(40% 60% at 50% 50%,rgba(20,40,120,.12),transparent 80%);
  animation:rfheroshift 12s ease-in-out infinite alternate}
@keyframes rfheroshift{
  0%{background:radial-gradient(70% 160% at 92% -10%,rgba(61,111,224,.7),transparent 58%),
      radial-gradient(55% 110% at 0% 130%,rgba(30,70,180,.28),transparent 65%)}
  100%{background:radial-gradient(70% 160% at 78% 10%,rgba(80,130,255,.65),transparent 60%),
       radial-gradient(55% 110% at 8% 100%,rgba(20,55,160,.32),transparent 68%)}}
.rf-hero::after{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background-image:__HERO_GRAIN__;opacity:.2;mix-blend-mode:screen}
.rf-traj{position:absolute;left:55%;right:0;top:14%;bottom:0;z-index:-1;pointer-events:none}
@media (max-width:1000px){.rf-traj{left:38%;opacity:.6}}
.rf-traj .rf-area,.rf-traj .rf-line{position:absolute;inset:0}
.rf-traj .rf-area{background:linear-gradient(180deg,rgba(111,155,255,.32),rgba(111,155,255,.04))}
.rf-traj .rf-line{background:rgba(244,241,234,.85)}
.rf-traj .rf-apex{position:absolute;width:11px;height:11px;margin:-5px 0 0 -5px;border-radius:50%;
  background:#b8d0ff;box-shadow:0 0 0 7px rgba(155,188,255,.22),0 0 32px 8px rgba(111,155,255,.6)}
.rf-top{display:flex;justify-content:space-between;align-items:center;gap:16px;
  font-family:'DM Mono',ui-monospace,monospace;font-size:10.5px;letter-spacing:.16em;
  text-transform:uppercase;color:rgba(244,241,234,.72)}
.rf-live{display:inline-flex;align-items:center;gap:9px}
.rf-live i{width:6px;height:6px;border-radius:50%;background:#9bbcff;animation:rfpulse 1.8s ease-in-out infinite}
@keyframes rfpulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.7)}}
.rf-title{font-weight:800;font-size:clamp(34px,4.3vw,66px);line-height:.92;letter-spacing:-.055em;
  margin:30px 0 14px;color:__PAPER__}
.rf-dot{display:inline-block;width:.12em;height:.12em;margin-left:.03em;border-radius:50%;background:#9bbcff}
.rf-sub{font-family:'DM Mono',ui-monospace,monospace;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:rgba(244,241,234,.68);margin:0 0 34px;max-width:60ch;line-height:1.7}
.rf-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:28px;
  border-top:1px solid rgba(244,241,234,.16);padding-top:16px;max-width:780px}
.rf-stat{display:flex;flex-direction:column;gap:3px;min-width:0}
.rf-l,.rf-s{font-family:'DM Mono',ui-monospace,monospace;font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:rgba(244,241,234,.62)}
.rf-v{font-weight:700;font-size:clamp(22px,2vw,30px);line-height:1.05;letter-spacing:-.035em;
  font-variant-numeric:lining-nums tabular-nums}
.rf-v small{font-family:'DM Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.08em;
  margin-left:5px;color:rgba(244,241,234,.7);font-weight:400}
.rf-stat.bad .rf-v,.rf-stat.bad .rf-s{color:#ff9aa6}
.rf-stats.learn{max-width:980px}
.rf-n{margin-top:8px;font-size:11.5px;line-height:1.5;color:rgba(244,241,234,.8)}
@media (max-width:1000px){.rf-hero{margin-left:-1rem;margin-right:-1rem;padding-left:1.5rem;padding-right:1.5rem}}
@media (max-width:760px){.rf-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}

/* Footer */
.rf-foot{position:relative;overflow:hidden;isolation:isolate;background:__NAVY__;color:rgba(244,241,234,.78);
  margin:48px -5rem -40px -5rem;padding:30px 5rem 34px;display:flex;justify-content:space-between;
  flex-wrap:wrap;gap:12px;font-family:'DM Mono',ui-monospace,monospace;font-size:10.5px;
  letter-spacing:.14em;text-transform:uppercase}
.rf-foot::after{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;
  background-image:__HERO_GRAIN__;opacity:.18;mix-blend-mode:screen}
.rf-foot i{display:inline-block;width:6px;height:6px;border-radius:50%;background:#9bbcff;margin-right:10px}
@media (max-width:1000px){.rf-foot{margin-left:-1rem;margin-right:-1rem;padding-left:1.5rem;padding-right:1.5rem}}
</style>
"""


def css(dark):
    # Page-wide styles. dark picks colours that read well on the active theme
    out = _CSS
    for key, val in {
        "__PAGE_GRAIN__": _grain((1, 1, 1) if dark else (0, 0, 0), 0.6),
        "__HERO_GRAIN__": _grain((1, 1, 1), 0.5),
        "__GRAIN_OPACITY__": ".05" if dark else ".11",
        "__BLEND__": "screen" if dark else "multiply",
        "__RULE__": "#1f2a44" if dark else "#cfc9bd",
        "__MUTED__": "#a39e95" if dark else "#5f5a51",
        "__ACCENT__": "#8fb2ff" if dark else "#12296b",
        "__NOTEBG__": "transparent",
        "__NAVY__": NAVY, "__PAPER__": PAPER,
    }.items():
        out = out.replace(key, val)
    return out


def eyebrow(number, text):
    return f'<div class="rf-eyebrow"><b>N°{number:02d}</b><span>{escape(text)}</span></div>'


def event_key(items):
    # items: (name, value text, colour) for each dashed line on the chart
    return '<div class="rf-key">' + "".join(
        f'<span><i style="color:{color}"></i><b style="color:{color}">{escape(name)}</b>'
        f'{escape(value)}</span>' for name, value, color in items) + "</div>"


def _trajectory(t, alt, apogee_t):
    # Altitude profile drawn with CSS clip-path shapes, with a glowing apogee dot.
    # (An image would have to be decoded again on every update, which flickers while
    # a slider is dragged; clip-paths repaint in the same frame.)
    # Only the start of the flight is drawn so the climb stays dramatic.
    end = t[-1] if apogee_t is None else min(t[-1], apogee_t * 3.2)
    keep = t <= end
    tt, aa = t[keep], alt[keep]
    idx = np.unique(np.linspace(0, len(tt) - 1, 140).astype(int))
    x = tt[idx] / end * 100
    y = 100 - 80 * aa[idx] / max(float(alt.max()), 1e-9)
    pts = [f"{a:.2f}% {b:.2f}%" for a, b in zip(x, y)]
    area = f"polygon(0% 100%, {', '.join(pts)}, {x[-1]:.2f}% 100%)"
    # A thin ribbon: the curve, then the same curve shifted 1.5 px down-right, reversed
    back = [f"calc({a:.2f}% + 1.5px) calc({b:.2f}% + 1.5px)" for a, b in zip(x[::-1], y[::-1])]
    line = f"polygon({', '.join(pts)}, {', '.join(back)})"
    apex = ""
    if apogee_t is not None:
        apex = f'<div class="rf-apex" style="left:{apogee_t / end * 100:.2f}%;top:20%"></div>'
    return (f'<div class="rf-traj"><div class="rf-area" style="clip-path:{area}"></div>'
            f'<div class="rf-line" style="clip-path:{line}"></div>{apex}</div>')


def hero(meta, stats, result, learn=False):
    # meta: short line under the title. stats: list of (label, value, unit, sub, bad)
    traj = _trajectory(result["t"], result["alt"], result["apogee_t"])
    cells = "".join(
        f'<div class="rf-stat{" bad" if bad else ""}"><span class="rf-l">{escape(label)}</span>'
        f'<span class="rf-v">{escape(value)}<small>{escape(unit)}</small></span>'
        f'<span class="rf-s">{escape(sub)}</span>'
        + (f'<span class="rf-n">{escape(note[0])}</span>' if note and note[0] else "") + '</div>'
        for label, value, unit, sub, bad, *note in stats)
    return (f'<div class="rf-hero">{traj}'
            '<div class="rf-top"><span>N°01 — Flight issue</span>'
            f'<span class="rf-live"><i></i>{escape(meta[0])}</span></div>'
            '<div class="rf-title">Rocket flight<br>simulator<span class="rf-dot"></span></div>'
            f'<p class="rf-sub">{escape(meta[1])}</p>'
            f'<div class="rf-stats{" learn" if learn else ""}">{cells}</div></div>')


def alert_banner(kind, icon, title, body):
    # kind: "red" or "green". Renders a custom-coloured alert banner via st.html.
    return (f'<div class="rf-alert {kind}">'
            f'<span class="rf-ai">{icon}</span>'
            f'<div class="rf-ab"><span class="rf-at">{escape(title)}</span>'
            f'<span>{escape(body)}</span></div></div>')


def metric_card(label, value, delta, note=None):
    # Drop-in for st.metric that accepts an optional note shown dimmed inside the card.
    # note is a plain-text string; pass None when Learn is off.
    note_html = (f'<p class="rf-cn">{escape(note)}</p>' if note else "")
    return (f'<div class="rf-card">'
            f'<span class="rf-cl">{escape(label)}</span>'
            f'<span class="rf-cv">{escape(value)}</span>'
            f'<span class="rf-cd">{escape(delta)}</span>'
            f'{note_html}</div>')


def footer():
    return ('<div class="rf-foot"><span><i></i>Rocket flight simulator</span>'
            '<span>Motor data thrustcurve.org</span><span>Validated against OpenRocket</span></div>')
