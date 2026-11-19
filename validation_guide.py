# The "how to match OpenRocket" guide shown in the Validation tab.

import math

import streamlit as st

R_AIR = 287.05  # J/(kg K), specific gas constant of dry air


def isa_pressure(altitude_m):
    # International Standard Atmosphere pressure in Pa
    return 101325.0 * (1 - 2.25577e-5 * altitude_m) ** 5.25588


def temperature_for_density(rho, altitude_m):
    # Air temperature in C that gives density rho at the launch altitude, at ISA pressure
    return isa_pressure(altitude_m) / (R_AIR * rho) - 273.15


def latitude_for_gravity(g):
    # Latitude (degrees) at which the standard gravity formula gives g at sea level
    def formula(lat):
        s = math.sin(math.radians(lat))
        s2 = math.sin(math.radians(2 * lat))
        return 9.780327 * (1 + 0.0053024 * s * s - 0.0000058 * s2 * s2)
    if not formula(0) <= g <= formula(90):
        return None
    lo, hi = 0.0, 90.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if formula(mid) < g else (lo, mid)
    return (lo + hi) / 2


def render(motor, rocket, env):
    st.markdown(
        "A simulator and OpenRocket only agree when both are fed the same physics. OpenRocket "
        "models far more than this simulator does, so you have to **switch those extras off or "
        "pin them to fixed values**. Work through the steps below, then export the flight and "
        "upload it here.")

    lat = latitude_for_gravity(env.g)
    temp = temperature_for_density(env.rho_pad, env.elevation)
    rows = [
        ("Motor", f"{motor.name.split('-')[0]}, ejection delay {motor.delay:g} s",
         "Sidebar, Motor"),
        ("Motor loaded / propellant mass",
         f"{motor.total_mass * 1000:.1f} g / {motor.prop_mass * 1000:.1f} g", "Sidebar, Motor"),
        ("Rocket mass without the motor", f"{rocket.dry_mass * 1000:.1f} g",
         "Sidebar, Rocket"),
        ("Body tube outer diameter", f"{rocket.diameter * 1000:.1f} mm", "Sidebar, Rocket"),
        ("Override drag coefficient", f"{rocket.cd:.2f}", "Sidebar, Rocket"),
        ("Parachute diameter / Cd", f"{rocket.chute_diameter * 100:.0f} cm / {rocket.chute_cd:.2f}",
         "Sidebar, Rocket"),
        ("Launch altitude", f"{env.elevation:.0f} m", "Sidebar, Environment"),
        ("Air temperature (non-standard atmosphere)",
         f"{temp:.1f} °C at {isa_pressure(env.elevation) / 100:.1f} mbar",
         f"Gives {env.rho_pad:.3f} kg/m³"),
        ("Latitude (sets gravity)",
         f"{lat:.1f}°" if lat is not None else "Out of range, OpenRocket cannot reach this gravity",
         f"Gives {env.g:.2f} m/s²"),
        ("Time step", f"{env.dt:g} s", "Sidebar, Safety and solver"),
    ]
    st.markdown("##### Values to enter in OpenRocket for your current settings")
    st.markdown("| Setting | Enter in OpenRocket | Comes from |\n|---|---|---|\n" +
                "\n".join(f"| {a} | **{b}** | {c} |" for a, b, c in rows))

    st.markdown("##### Steps in OpenRocket")
    st.markdown(
        "Menu names vary a little between OpenRocket versions, but each of these exists in every "
        "recent one.\n\n"
        "1. **Build one stage.** Set the body tube outer diameter from the table. Nose cone and "
        "fins can be anything, because the drag is overridden in the next step.\n"
        "2. **Pin the mass and the drag.** Double-click the rocket, open its **Override** tab, "
        "tick **Override mass** and enter the mass without the motor, then tick **Override CD** "
        "and enter the drag coefficient. Tick the option that applies the override to all "
        "subcomponents so that no part adds its own mass or drag. Leave the reference area at "
        "the default (maximum diameter), which is the same area this simulator uses.\n"
        "3. **Add the parachute.** Set its diameter and drag coefficient from the table. Set "
        "**Deploys at: Motor ejection charge** with a delay of 0 s. Do not use apogee or an "
        "altitude trigger, because this simulator always fires the chute at burnout plus the "
        "motor delay.\n"
        "4. **Choose the same motor.** Pick the Estes motor with the same letter, number and "
        "delay. Open the motor details and check that the loaded and propellant masses match the "
        "table. If they differ, change them in OpenRocket or in the sidebar here.\n"
        "5. **Remove every disturbance.** In **Simulation, Edit, Launch conditions** set wind "
        "speed 0, turbulence 0 and launch rod angle 0° (straight up). Set the launch altitude "
        "from the table. Turn off *Use International Standard Atmosphere* and enter the "
        "temperature and pressure from the table. Enter the latitude from the table.\n"
        "6. **Match the solver.** In the simulation options set the time step to the value in the "
        "table (OpenRocket defaults to 0.05 s) and the geodetic computation to **Flat Earth**, "
        "so there is no Coriolis effect or Earth curvature.\n"
        "7. **Run, then export.** Open the Plot / Export data tab and choose Export data. Pick "
        "exactly four variables in this order: **Time, Altitude, Vertical velocity, Vertical "
        "acceleration**. Use SI units, a comma as the separator and `#` as the comment "
        "character. Save the file, then upload it above.")

    st.markdown("##### Caveats that cause a mismatch")
    st.markdown(
        "- **Drag is the biggest one.** OpenRocket normally builds drag from every part and "
        "changes it with Mach and Reynolds number. This simulator uses one constant value. Either "
        "override the drag in OpenRocket (step 2), or run the flight without the override, read the "
        "average *Drag coefficient* from OpenRocket's plot during the climb, and type that into the "
        "sidebar.\n"
        "- **Vertical only.** This is a 1-D model. Any wind, launch angle or weathercocking in "
        "OpenRocket lowers its apogee and cannot be matched here.\n"
        "- **Total versus vertical.** Export *Vertical* velocity and acceleration, not *Total*. "
        "Total values are always positive and will not line up with the signed values used here.\n"
        "- **Atmosphere.** OpenRocket uses a temperature-based model, and this simulator uses "
        "a simple exponential one, so a gap below about 1% is normal even with matching "
        "ground density.\n"
        "- **Gravity.** OpenRocket cannot take a gravity value. It computes it from latitude and "
        "altitude, which is why the table gives a latitude.\n"
        "- **Mass loss.** This simulator burns propellant steadily over the burn. OpenRocket may "
        "distribute it differently, which changes the acceleration trace slightly during boost.\n"
        "- **Integration.** OpenRocket uses a Runge-Kutta method and this simulator uses "
        "semi-implicit Euler. With a time step of 0.01 s or less the difference is tiny.\n"
        "- **Parachute opening.** Both open instantly and fully. Real parachutes and "
        "OpenRocket's inflation, if enabled in your version, change the first seconds after "
        "ejection.\n"
        "- **Altitude reference.** Keep the launch altitude at the same value in both programs, "
        "or at 0 m, so that both measure height above the pad.\n"
        "- **File format.** The CSV must have four numeric columns. Any text line must start "
        "with `#`, or the file cannot be read. Repeated time stamps at flight events are fine.")

    st.markdown("##### Reading the result")
    st.markdown(
        "- **Apogee within about 1%** and **RMS altitude error under a few metres** is a good "
        "match for a small rocket.\n"
        "- **Apogee too high here:** raise the drag coefficient in the sidebar. **Too low:** "
        "lower it. Repeat until the apogee matches, then check the flight time.\n"
        "- **Apogee right but flight time off:** check the parachute diameter, parachute drag "
        "coefficient and ejection delay.\n"
        "- **Burnout speed off:** check the motor, its masses, and the dry mass.\n"
        "- **Velocity or acceleration spikes at burnout:** these are sharp in a 1-D model. Compare "
        "the altitude curve first, because it hides them.")
