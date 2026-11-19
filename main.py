# Time-stepped integration of a model rocket's flight using real motor thrust
# curves (thrustcurve.org), linear propellant mass loss, quadratic aerodynamic
# drag (with altitude-dependent air density), and parachute deployment after the motor's delay charge.
# Run `python main.py` to simulate an Estes Alpha III on a C6 motor, check
# time-step convergence, compare B6/C6/D12 motors and sweep mass and drag.

import bisect
import csv
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

G = 9.81    # gravitational acceleration, m/s^2
RHO = 1.2   # sea-level air density, kg/m^3
SCALE_HEIGHT = 8500.0  # m, exponential atmosphere scale height

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
IMAGE_DIR = HERE / "images"


def air_density(alt, rho0=RHO, scale_height=SCALE_HEIGHT):
    # Exponential atmosphere model: density falls off with altitude
    return rho0 * np.exp(-alt / scale_height)


# Models
@dataclass
class Motor:
    name: str
    times: list        # s
    thrusts: list      # N
    total_mass: float  # kg, loaded motor
    prop_mass: float   # kg, propellant only
    delay: float       # s, ejection charge delay after burnout

    @property
    def burn_time(self):
        return self.times[-1]

    def thrust(self, t):
        # Thrust at time t, interpolated linearly from the data table, and zero after
        # burnout. Same result as np.interp(t, times, thrusts, right=0), but plain
        # Python is several times faster for one value at a time, which keeps the
        # app responsive while sliders are dragged.
        times, thrusts = self.times, self.thrusts
        if t > times[-1]:
            return 0.0
        if t <= times[0]:
            return float(thrusts[0])
        i = bisect.bisect_right(times, t)
        if i >= len(times):
            return float(thrusts[-1])
        t0, t1 = times[i - 1], times[i]
        f0, f1 = thrusts[i - 1], thrusts[i]
        return float(f0 + (f1 - f0) * (t - t0) / (t1 - t0))

    def mass(self, t):
        # Motor mass at time t, with propellant burning off linearly
        frac = min(max(t / self.burn_time, 0.0), 1.0)
        return self.total_mass - self.prop_mass * frac


@dataclass
class Rocket:
    dry_mass: float               # kg, excluding the motor
    diameter: float               # m, body tube
    cd: float                     # body drag coefficient
    chute_diameter: float = 0.30  # m
    chute_cd: float = 0.8

    @property
    def area(self):
        return np.pi * (self.diameter / 2) ** 2

    @property
    def chute_area(self):
        return np.pi * (self.chute_diameter / 2) ** 2


#  Motor files
def load_thrust_csv(path, name, total_mass, prop_mass, delay):
    # Load a thrustcurve.org CSV (metadata lines, then time/thrust rows)
    times, thrusts = [0.0], [0.0]
    for row in csv.reader(Path(path).read_text().splitlines()):
        try:
            t, f = float(row[0]), float(row[1])
        except (ValueError, IndexError):
            continue
        times.append(t)
        thrusts.append(f)
    return Motor(name, times, thrusts, total_mass, prop_mass, delay)


def load_eng(path, name, delay):
    # Load a RASP .eng file from disk
    return parse_eng(Path(path).read_text(), name, delay)


def parse_eng(text, name, delay):
    # Parse RASP .eng text. Masses come from the header line
    times, thrusts = [0.0], [0.0]
    header = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if header is None:
            header = parts
            continue
        times.append(float(parts[0]))
        thrusts.append(float(parts[1]))
    return Motor(name, times, thrusts, total_mass=float(header[5]),
                 prop_mass=float(header[4]), delay=delay)


B6 = load_eng(DATA_DIR / "Estes_B6.eng", "B6-4", delay=4.0)
C6 = load_thrust_csv(DATA_DIR / "Estes_C6.csv", "C6-5", total_mass=0.0240,
                     prop_mass=0.0123, delay=5.0)
D12 = load_eng(DATA_DIR / "Estes_D12.eng", "D12-5", delay=5.0)

ALPHA_III = Rocket(dry_mass=0.0482, diameter=0.0248, cd=0.63)


# Simulation
def simulate(motor, rocket, dt=0.01, max_time=300.0, g=G, rho0=RHO,
             scale_height=SCALE_HEIGHT):
    # Simulate one flight and return time series plus summary values.
    # g, rho0 (air density at the launch pad) and scale_height set the environment
    t, alt, vel = 0.0, 0.0, 0.0
    phase = "pad"
    apogee_alt = apogee_t = burnout_t = None
    chute_out = False
    ts, alts, vels, accs = [], [], [], []

    while t < max_time:
        thrust = motor.thrust(t)
        mass = rocket.dry_mass + motor.mass(t)
        weight = mass * g

        # Flight phase logic
        if phase == "pad" and thrust > weight:
            phase = "boost"
        elif phase == "boost" and t >= motor.burn_time:
            phase, burnout_t = "coast", t
        elif phase in ("boost", "coast") and vel < 0 and apogee_t is None:
            apogee_alt, apogee_t = alt, t
            phase = "descent"

        if burnout_t is not None and t >= burnout_t + motor.delay:
            chute_out = True

        # Forces
        if phase == "pad":
            acc = 0.0
        else:
            cd_a = (rocket.chute_cd * rocket.chute_area if chute_out
                    else rocket.cd * rocket.area)
            drag = 0.5 * air_density(alt, rho0, scale_height) * vel ** 2 * cd_a
            if vel > 0:
                acc = (thrust - weight - drag) / mass
            else:
                acc = (thrust - weight + drag) / mass

        ts.append(t)
        alts.append(alt)
        vels.append(vel)
        accs.append(acc)

        # Semi-implicit Euler step
        vel += acc * dt
        alt += vel * dt
        t += dt

        if phase != "pad" and alt <= 0.0:
            ts.append(t)
            alts.append(0.0)
            vels.append(0.0)
            accs.append(0.0)
            break

    ts, alts, vels, accs = map(np.array, (ts, alts, vels, accs))
    return {
        "motor": motor.name,
        "t": ts, "alt": alts, "vel": vels, "acc": accs,
        "apogee": apogee_alt if apogee_alt is not None else alts.max(),
        "apogee_t": apogee_t,
        "burnout_t": burnout_t,
        "chute_t": burnout_t + motor.delay if burnout_t is not None else None,
        "max_speed": np.abs(vels).max(),
        "max_acc_g": accs.max() / G,
        "flight_time": ts[-1],
    }


# Output
def print_summary(r):
    print(f"--- {r['motor']} ---")
    print(f"Max altitude : {r['apogee']:.1f} m (t = {r['apogee_t']:.2f} s)")
    print(f"Max speed    : {r['max_speed']:.1f} m/s")
    print(f"Max accel    : {r['max_acc_g']:.1f} g")
    print(f"Burnout time : {r['burnout_t']:.2f} s")
    print(f"Chute deploy : {r['chute_t']:.2f} s")
    print(f"Flight time  : {r['flight_time']:.1f} s")


def plot_flight(r, path):
    fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    series = (("alt", "Altitude (m)"), ("vel", "Velocity (m/s)"),
              ("acc", "Acceleration (m/s²)"))
    for ax, (key, label) in zip(axes, series):
        ax.plot(r["t"], r[key], lw=1.5)
        ax.axvline(r["apogee_t"], color="gray", ls=":", lw=1)
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
    axes[0].plot(r["apogee_t"], r["apogee"], "ro")
    axes[0].annotate(f"Apogee {r['apogee']:.0f} m",
                     (r["apogee_t"], r["apogee"]),
                     textcoords="offset points", xytext=(10, -5))
    axes[0].set_title(f"Flight: {r['motor']}")
    axes[-1].set_xlabel("Time (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def dt_convergence(motor, rocket):
    # Print apogee for decreasing time steps to show the result converges
    print("\nTime-step convergence:")
    for dt in (0.1, 0.01, 0.001):
        apogee = simulate(motor, rocket, dt)["apogee"]
        print(f"  dt = {dt:<6} apogee = {apogee:.2f} m")


def compare_motors(rocket, motors, path):
    fig, ax = plt.subplots(figsize=(8, 5))
    for m in motors:
        r = simulate(m, rocket)
        ax.plot(r["t"], r["alt"], label=f"{m.name} ({r['apogee']:.0f} m)")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Altitude (m)")
    ax.set_title("Motor comparison")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def sweep(motor, rocket, path):
    # Plot apogee against dry mass and against drag coefficient
    masses = np.linspace(0.030, 0.080, 20)
    cds = np.linspace(0.4, 0.9, 20)
    by_mass = [simulate(motor, replace(rocket, dry_mass=m))["apogee"]
               for m in masses]
    by_cd = [simulate(motor, replace(rocket, cd=c))["apogee"] for c in cds]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(masses * 1000, by_mass)
    ax1.set_xlabel("Dry mass (g)")
    ax1.set_ylabel("Apogee (m)")
    ax2.plot(cds, by_cd)
    ax2.set_xlabel("Drag coefficient")
    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
    fig.suptitle(f"Apogee sweeps ({motor.name})")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def validate(result, csv_path, path):
    # Overlay the simulation on an OpenRocket CSV export and print the error
    ref = np.loadtxt(csv_path, delimiter=",", comments="#")
    t_ref, alt_ref, vel_ref, acc_ref = ref.T
    alt_sim = np.interp(t_ref, result["t"], result["alt"])
    err = alt_sim - alt_ref

    print("\nComparison with OpenRocket:")
    print(f"  Apogee       : {result['apogee']:.1f} m vs {alt_ref.max():.1f} m "
          f"({100 * (result['apogee'] / alt_ref.max() - 1):+.1f}%)")
    print(f"  Flight time  : {result['flight_time']:.1f} s vs {t_ref[-1]:.1f} s")
    print(f"  Altitude error: RMS {np.sqrt(np.mean(err ** 2)):.1f} m, "
          f"max {np.abs(err).max():.1f} m")

    fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    rows = (("alt", alt_ref, "Altitude (m)"),
            ("vel", vel_ref, "Velocity (m/s)"),
            ("acc", acc_ref, "Acceleration (m/s²)"))
    for ax, (key, ref_y, label) in zip(axes, rows):
        ax.plot(t_ref, ref_y, lw=2.5, color="tab:orange", label="OpenRocket")
        ax.plot(result["t"], result[key], lw=1.2, color="tab:blue", label="This sim")
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
    axes[0].legend()
    axes[0].set_title("Validation against OpenRocket")
    axes[-1].set_xlabel("Time (s)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    result = simulate(C6, ALPHA_III)
    for motor in (B6, C6, D12):
        print_summary(result if motor is C6 else simulate(motor, ALPHA_III))
        print()
    dt_convergence(C6, ALPHA_III)

    reference = DATA_DIR / "openrocket.csv"
    if reference.exists():
        validate(result, reference, IMAGE_DIR / "validation.png")

    plot_flight(result, IMAGE_DIR / "flight.png")
    compare_motors(ALPHA_III, [B6, C6, D12], IMAGE_DIR / "motors.png")
    sweep(C6, ALPHA_III, IMAGE_DIR / "sweep.png")
    print("\nSaved plots to images/")

    print("Opening the app in your browser (Ctrl+C to stop)...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(HERE / "app.py")])


if __name__ == "__main__":
    main()

