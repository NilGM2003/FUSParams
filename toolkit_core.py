"""Calculation core for the Transducer Toolkit (no GUI code here).

Mirrors the four original scripts:
    focus_analysis()   <- focus.py     (O'Neil focal size of a spherical bowl)
    design_sweep()     <- foc_calc.py  (R needed for a target lateral width vs frequency)
    band_profiles()    <- band.py      (axial profile for a burst + finite bandwidth)
    rotation_margin()  <- margin.py    (rotation margin vs culture plate)

Only numpy is needed (J1 and the root finder are implemented here, so scipy
is not required and the executable stays smaller).
"""

import math

import numpy as np

J1_ZERO = 3.8317059702075125   # first zero of the Bessel function J1


# --------------------------------------------------------------------------
# Small numerical helpers
# --------------------------------------------------------------------------
def j1(x):
    """Bessel function J1 via its integral form (exact for a periodic integrand)."""
    x = np.asarray(x, float)
    tau = np.linspace(0.0, 2.0 * np.pi, 512, endpoint=False)
    return np.mean(np.cos(tau - x[..., None] * np.sin(tau)), axis=-1)


def airy(x):
    """Airy pattern 2*J1(x)/x (equal to 1 at x = 0)."""
    x = np.asarray(x, float)
    safe = np.where(np.abs(x) < 1e-9, 1.0, x)
    return np.where(np.abs(x) < 1e-9, 1.0, 2.0 * j1(safe) / safe)


def bisect(fn, lo, hi, tol=1e-12, max_iter=200):
    flo, fhi = fn(lo), fn(hi)
    if flo * fhi > 0:
        raise ValueError("root not bracketed")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = fn(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def x_for_level(dB):
    """Airy argument x where 2*J1(x)/x has dropped by dB (first lobe)."""
    ratio = 10.0 ** (-dB / 20.0)
    return bisect(lambda x: float(airy(x)) - ratio, 1e-6, J1_ZERO)


def bowl_depth(a, R):
    return R - math.sqrt(R * R - a * a)


def check_geometry(a, R):
    if a <= 0 or R <= 0:
        raise ValueError("Aperture radius and radius of curvature must be positive.")
    if a > R:
        raise ValueError("Aperture radius cannot exceed the radius of curvature (a <= R).")


# --------------------------------------------------------------------------
# O'Neil on-axis pressure
# --------------------------------------------------------------------------
def p_axial(z, k, a, R):
    """Exact on-axis pressure amplitude of a spherical bowl (arbitrary units).

    z is measured from the bowl centre (the point on the bowl surface on axis).
    """
    h = bowl_depth(a, R)
    z = np.asarray(z, float)
    z = np.where(np.abs(z - R) < 1e-9, R + 1e-9, z)      # avoid 0/0 at z = R
    return np.abs(2.0 / (1.0 - z / R) *
                  np.sin(k / 2.0 * (np.sqrt((z - h) ** 2 + a ** 2) - z)))


def crossings(z, p, level):
    """All z where p crosses `level` (linear interpolation between samples)."""
    s = p - level
    idx = np.where(np.sign(s[:-1]) != np.sign(s[1:]))[0]
    return z[idx] + (z[idx + 1] - z[idx]) * s[idx] / (s[idx] - s[idx + 1])


def main_lobe(z, p, dB):
    """Contiguous main lobe (z1, z2) around the peak at -dB, or None if the
    level is not crossed on both sides inside the scanned range."""
    i_pk = int(p.argmax())
    zc = crossings(z, p, p[i_pk] * 10.0 ** (-dB / 20.0))
    near, far = zc[zc < z[i_pk]], zc[zc > z[i_pk]]
    if near.size == 0 or far.size == 0:
        return None
    return float(near.max()), float(far.min())


# --------------------------------------------------------------------------
# focus.py  ->  focal size of a given transducer
# --------------------------------------------------------------------------
def focus_analysis(c, f, a, R, zmin, zmax, npts=40001, levels=(3, 6, 12)):
    check_geometry(a, R)
    if zmax <= zmin or zmin <= 0:
        raise ValueError("z range must satisfy 0 < z min < z max.")
    lam = c / f
    k = 2 * np.pi / lam
    h = bowl_depth(a, R)

    z = np.linspace(zmin, zmax, npts)
    p = p_axial(z, k, a, R)
    i_pk = int(p.argmax())
    z_pk, p_pk = float(z[i_pk]), float(p[i_pk])

    axial = {}
    for dB in levels:
        zc = crossings(z, p, p_pk * 10.0 ** (-dB / 20.0))
        near, far = zc[zc < z_pk], zc[zc > z_pk]
        entry = {"all": zc, "contiguous": None, "outermost": None}
        if near.size and far.size:
            entry["contiguous"] = (float(near.max()), float(far.min()))
            entry["outermost"] = (float(near.min()), float(far.max()))
        axial[dB] = entry

    lateral = {}
    for dB in levels:
        x = x_for_level(dB)
        lateral[dB] = 2 * x * R / (k * a)
    null_diameter = 2 * J1_ZERO * R / (k * a)

    return dict(lam=lam, k=k, h=h, z=z, p=p, z_pk=z_pk, p_pk=p_pk,
                gain=k * h, half_angle=math.degrees(math.asin(a / R)),
                f_number=R / (2 * a), axial=axial, lateral=lateral,
                null_diameter=null_diameter)


def lateral_profile_db(k, a, R, r):
    """Airy focal-plane profile in dB for radial positions r (m)."""
    amp = np.abs(airy(k * a * r / R))
    return 20 * np.log10(np.maximum(amp, 1e-4))


# --------------------------------------------------------------------------
# foc_calc.py  ->  design: which R gives a target lateral width?
# --------------------------------------------------------------------------
def lateral_width(c, f, a, R, dB=6):
    k = 2 * np.pi * f / c
    return 2 * x_for_level(dB) * R / (k * a)


def axial_length_design(c, f, a, R, dB=6):
    """Contiguous main-lobe length and peak position (m) from the exact formula."""
    k = 2 * np.pi * f / c
    z = np.linspace(0.3 * R, 1.6 * R, 40001)
    p = p_axial(z, k, a, R)
    z_pk = float(z[int(p.argmax())])
    lobe = main_lobe(z, p, dB)
    return (float("nan") if lobe is None else lobe[1] - lobe[0]), z_pk


def design_sweep(c, W_target, a, dB, f_values):
    x = x_for_level(dB)
    rows = []
    for f in f_values:
        k = 2 * np.pi * f / c
        R = W_target * k * a / (2 * x)
        if R <= a:
            rows.append(dict(f=f, R=R, feasible=False))
            continue
        length, z_pk = axial_length_design(c, f, a, R, dB)
        rows.append(dict(f=f, R=R, feasible=True, f_number=R / (2 * a),
                         half_angle=math.degrees(math.asin(a / R)),
                         axial=length, z_pk=z_pk))
    return rows


# --------------------------------------------------------------------------
# band.py  ->  burst + finite bandwidth
# --------------------------------------------------------------------------
def _next_pow2(n):
    return 1 << int(math.ceil(math.log2(max(n, 2))))


def band_profiles(c, f0, a, R, z, cases, chunk=150):
    """Peak-pressure axial profiles for several (n_cycles, fractional bandwidth).

    Returns (list of absolute peak profiles, CW reference profile). Units are
    arbitrary but common, so profiles can be compared in absolute terms.
    """
    check_geometry(a, R)
    h = bowl_depth(a, R)
    z = np.asarray(z, float)
    zz = np.where(np.abs(z - R) < 1e-9, R + 1e-9, z)
    d = np.sqrt((zz - h) ** 2 + a ** 2)
    delta = d - zz
    max_delay = float(np.max(np.abs(delta))) / c

    fs = 16 * f0
    n_max = max(n for n, _ in cases)
    fbw_min = min(b for _, b in cases)
    guard = max(20e-6, 2.0 / (fbw_min * f0))
    t0 = guard
    nt = _next_pow2(int(fs * (t0 + n_max / f0 + max_delay + guard)))
    t = np.arange(nt) / fs
    f = np.fft.rfftfreq(nt, 1 / fs)
    k = 2 * np.pi * f / c

    profiles = []
    for n_cycles, fbw in cases:
        # Hann-windowed toneburst
        x = np.zeros(nt)
        m = (t >= t0) & (t < t0 + n_cycles / f0)
        tau = t[m] - t0
        x[m] = np.sin(2 * np.pi * f0 * tau) * np.sin(np.pi * tau * f0 / n_cycles) ** 2
        # Gaussian transducer response (fractional -6 dB bandwidth)
        sigma = (fbw * f0 / 2) / np.sqrt(2 * np.log(2))
        S = np.fft.rfft(x) * np.exp(-(f - f0) ** 2 / (2 * sigma ** 2))

        peak = np.zeros(z.size)
        for i0 in range(0, z.size, chunk):
            sl = slice(i0, i0 + chunk)
            G = (1 - np.exp(-1j * np.outer(delta[sl], k))) / (1 - zz[sl] / R)[:, None]
            p_t = np.fft.irfft(S[None, :] * G, nt, axis=1)
            peak[sl] = np.abs(p_t).max(axis=1)
        profiles.append(peak)

    cw = p_axial(z, 2 * np.pi * f0 / c, a, R)
    return profiles, cw


# --------------------------------------------------------------------------
# margin.py  ->  rotation margin vs culture plate
# --------------------------------------------------------------------------
def rotation_margin(radius_of_curvature, aperture_diameter, plate_d, plate_h):
    """Same logic as margin.py (all lengths in the same unit, e.g. mm)."""
    if radius_of_curvature <= 0:
        raise ValueError("Radius of curvature must be greater than zero.")
    if aperture_diameter < 0:
        raise ValueError("Aperture diameter must not be negative.")
    if aperture_diameter > 2 * radius_of_curvature:
        raise ValueError("Aperture diameter cannot exceed the sphere's diameter.")
    if plate_d <= 0:
        raise ValueError("Plate diameter must be greater than zero.")
    if plate_h <= 0:
        raise ValueError("Plate height must be greater than zero.")

    plate_r = plate_d / 2
    critical_angle = math.degrees(math.atan(plate_h / plate_r))
    aperture_radius = aperture_diameter / 2
    aperture_angle = math.degrees(math.asin(aperture_radius / radius_of_curvature))
    sagitta = radius_of_curvature - math.sqrt(radius_of_curvature ** 2 - aperture_radius ** 2)
    focus_to_plate = radius_of_curvature - sagitta
    margin = (90 - critical_angle) - aperture_angle
    return dict(critical_angle=critical_angle, aperture_angle=aperture_angle,
                sagitta=sagitta, focus_to_plate=focus_to_plate, margin=margin)
