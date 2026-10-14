"""Transducer Toolkit - tkinter interface for the focal-size calculations.

Tabs (one per original script):
    1. Focal size          (focus.py)    O'Neil focal size of a given bowl
    2. Design              (foc_calc.py) R needed for a target lateral width vs frequency
    3. Burst & bandwidth   (band.py)     axial profile for a burst + finite bandwidth
    4. Rotation margin     (margin.py)   transducer rotation margin vs culture plate

All numerical work lives in toolkit_core.py.
"""

import csv
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

import toolkit_core as core

APP_NAME = "Transducer Toolkit"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def resource_path(name):
    """Path of a bundled file (works from source and inside a PyInstaller exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def num(var, name, positive=True):
    """Read a float from a StringVar (accepts a decimal comma)."""
    try:
        v = float(var.get().strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"'{name}' must be a number.")
    if positive and v <= 0:
        raise ValueError(f"'{name}' must be greater than zero.")
    return v


def lobe_text(lobe):
    if lobe is None:
        return "not crossed on both sides inside the z range"
    z1, z2 = lobe
    return f"{z1*1e3:.1f} to {z2*1e3:.1f} mm  (length {(z2-z1)*1e3:.1f} mm)"


class ResultBox(ttk.Frame):
    """Read-only monospace text area with a scrollbar."""

    def __init__(self, parent, height=12):
        super().__init__(parent)
        self.text = tk.Text(self, height=height, wrap="none", font="TkFixedFont")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def set(self, content):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")

    def get(self):
        return self.text.get("1.0", "end").rstrip()


class PlotPanel(ttk.Frame):
    """Matplotlib figure with the standard toolbar (zoom, pan, save image)."""

    def __init__(self, parent, figsize=(6.2, 4.2)):
        super().__init__(parent)
        self.fig = Figure(figsize=figsize, dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def draw(self):
        try:
            self.fig.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()


class BaseTab(ttk.Frame):
    """Left column = inputs and buttons, right column = results and plots."""

    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.left = ttk.Frame(self)
        self.left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.right = ttk.Frame(self)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.vars = {}

    def add_inputs(self, title, fields):
        box = ttk.LabelFrame(self.left, text=title, padding=8)
        box.pack(fill="x")
        for r, (key, label, default, unit) in enumerate(fields):
            ttk.Label(box, text=label).grid(row=r, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=str(default))
            self.vars[key] = v
            ttk.Entry(box, textvariable=v, width=10).grid(row=r, column=1, padx=4)
            ttk.Label(box, text=unit).grid(row=r, column=2, sticky="w")
        return box

    def add_buttons(self, buttons):
        row = ttk.Frame(self.left)
        row.pack(fill="x", pady=8)
        for text, cmd in buttons:
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=(0, 6))
        return row

    def add_note(self, text):
        ttk.Label(self.left, text=text, wraplength=260, justify="left",
                  foreground="#555555").pack(fill="x", pady=(4, 0))

    def val(self, key, name=None, positive=True):
        return num(self.vars[key], name or key, positive)

    def run(self):
        try:
            self.calculate()
        except ValueError as e:
            messagebox.showerror("Input error", str(e))
        except Exception as e:  # keep the window alive in the windowed exe
            messagebox.showerror("Error", f"{type(e).__name__}: {e}")

    def save_text(self, box, default_name):
        content = box.get()
        if not content:
            messagebox.showinfo("Nothing to save", "Run a calculation first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=default_name,
                                            filetypes=[("Text file", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content + "\n")


# --------------------------------------------------------------------------
# Tab 1: focus.py
# --------------------------------------------------------------------------
class FocusTab(BaseTab):
    MEDIA = {"Water 20 °C (1482 m/s)": 1482.0,
             "Water 37 °C (1524 m/s)": 1524.0,
             "Custom": None}

    def __init__(self, parent):
        super().__init__(parent)
        box = self.add_inputs("Transducer and medium", [
            ("c", "Sound speed c", 1482, "m/s"),
            ("f", "Frequency f", 500, "kHz"),
            ("a", "Aperture radius a", 21.5, "mm"),
            ("R", "Radius of curvature R", 30, "mm"),
            ("zmin", "z scan start", 12, "mm"),
            ("zmax", "z scan end", 45, "mm"),
        ])
        ttk.Label(box, text="Medium").grid(row=10, column=0, sticky="w", pady=(6, 0))
        self.medium = ttk.Combobox(box, values=list(self.MEDIA), state="readonly", width=22)
        self.medium.set("Water 20 °C (1482 m/s)")
        self.medium.grid(row=10, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.medium.bind("<<ComboboxSelected>>", self.on_medium)

        self.add_buttons([("Calculate", self.run), ("Load TS982", self.load_ts982),
                          ("Save results…", lambda: self.save_text(self.out, "focal_size.txt"))])
        self.add_note("O'Neil model: ideal rigid bowl, single frequency (CW), lossless linear "
                      "medium. z is measured from the bowl centre. The lateral size uses the "
                      "Airy approximation, which is less accurate for deep bowls.")

        self.right.rowconfigure(1, weight=1)
        self.right.columnconfigure(0, weight=1)
        self.out = ResultBox(self.right, height=17)
        self.out.grid(row=0, column=0, sticky="ew")
        self.plot = PlotPanel(self.right)
        self.plot.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

    def on_medium(self, _event=None):
        c = self.MEDIA.get(self.medium.get())
        if c is not None:
            self.vars["c"].set(str(c))

    def load_ts982(self):
        for key, v in dict(c=1482, f=500, a=21.5, R=30, zmin=12, zmax=45).items():
            self.vars[key].set(str(v))
        self.medium.set("Water 20 °C (1482 m/s)")
        self.run()

    def calculate(self):
        c = self.val("c", "Sound speed")
        f = self.val("f", "Frequency") * 1e3
        a = self.val("a", "Aperture radius") * 1e-3
        R = self.val("R", "Radius of curvature") * 1e-3
        zmin = self.val("zmin", "z scan start") * 1e-3
        zmax = self.val("zmax", "z scan end") * 1e-3
        r = core.focus_analysis(c, f, a, R, zmin, zmax)

        L = [f"GEOMETRY  (c = {c:g} m/s, f = {f/1e3:g} kHz)",
             f"  wavelength               {r['lam']*1e3:.2f} mm",
             f"  half-aperture angle      {r['half_angle']:.1f} deg",
             f"  F-number (R/D)           {r['f_number']:.2f}",
             f"  bowl depth h             {r['h']*1e3:.1f} mm",
             f"  focal gain k*h           {r['gain']:.1f}",
             "",
             "AXIAL  (z from bowl centre)",
             f"  pressure peak at z = {r['z_pk']*1e3:.1f} mm  "
             f"({abs(R - r['z_pk'])*1e3:.1f} mm "
             f"{'before' if r['z_pk'] < R else 'beyond'} the geometric focus at {R*1e3:g} mm)"]
        for dB, e in r["axial"].items():
            L.append(f"  -{dB} dB crossings (mm): {np.round(e['all']*1e3, 1)}")
            L.append(f"      contiguous main lobe: {lobe_text(e['contiguous'])}")
            L.append(f"      outermost crossings:  {lobe_text(e['outermost'])}")
        L += ["", "LATERAL  (focal plane, Airy approximation)"]
        for dB, w in r["lateral"].items():
            L.append(f"  -{dB} dB width           {w*1e3:.2f} mm")
        L.append(f"  first null diameter      {r['null_diameter']*1e3:.2f} mm")
        lobe6 = r["axial"][6]["contiguous"]
        if lobe6:
            d = r["lateral"][6]
            ln = lobe6[1] - lobe6[0]
            L += ["", f"-6 dB focal volume (ellipsoid, {d*1e3:.1f} x {d*1e3:.1f} x {ln*1e3:.1f} mm)"
                      f" = {np.pi/6*d*d*ln*1e9:.0f} mm^3"]
        self.out.set("\n".join(L))

        fig = self.plot.fig
        fig.clear()
        ax1, ax2 = fig.add_subplot(211), fig.add_subplot(212)
        z, p = r["z"], r["p"]
        ax1.plot(z * 1e3, 20 * np.log10(p / r["p_pk"]))
        for dB in (3, 6, 12):
            ax1.axhline(-dB, color="gray", ls="--", lw=0.8)
        ax1.axvline(R * 1e3, color="tab:red", ls=":", lw=1, label="geometric focus")
        ax1.axvline(r["z_pk"] * 1e3, color="tab:green", ls=":", lw=1, label="pressure peak")
        ax1.set_ylim(-20, 1)
        ax1.set_xlabel("z from bowl centre (mm)")
        ax1.set_ylabel("Pressure (dB re peak)")
        ax1.set_title("Axial profile")
        ax1.legend(loc="lower left", fontsize=8)
        ax1.grid(True)

        rmax = 0.8 * r["null_diameter"]
        rr = np.linspace(-rmax, rmax, 801)
        ax2.plot(rr * 1e3, core.lateral_profile_db(r["k"], a, R, rr))
        for dB in (3, 6, 12):
            ax2.axhline(-dB, color="gray", ls="--", lw=0.8)
        ax2.set_ylim(-30, 1)
        ax2.set_xlabel("Transverse position (mm)")
        ax2.set_ylabel("Pressure (dB re peak)")
        ax2.set_title("Lateral profile in the focal plane (Airy)")
        ax2.grid(True)
        self.plot.draw()


# --------------------------------------------------------------------------
# Tab 2: foc_calc.py
# --------------------------------------------------------------------------
class DesignTab(BaseTab):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        self.add_inputs("Target and fixed parameters", [
            ("W", "Target lateral width", 8, "mm"),
            ("dB", "Width defined at", 6, "-dB"),
            ("a", "Aperture radius a", 10, "mm"),
            ("c", "Sound speed c", 1482, "m/s"),
            ("fa", "Frequency from", 300, "kHz"),
            ("fb", "Frequency to", 1000, "kHz"),
            ("fs", "Frequency step", 100, "kHz"),
        ])
        self.add_buttons([("Calculate", self.run), ("Save CSV…", self.save_csv)])
        self.add_note("For each frequency the radius of curvature R is solved from the Airy "
                      "relation W = 2x R / (k a), then the axial length (contiguous main lobe, "
                      "same level) comes from the exact O'Neil on-axis formula. The lateral width "
                      "fixes only the product wavelength x F-number, so the axial length and R "
                      "follow from the frequency you pick.")

        self.right.rowconfigure(0, weight=1)
        self.right.rowconfigure(1, weight=2)
        self.right.columnconfigure(0, weight=1)
        cols = ("f", "R", "F", "ang", "axial", "zpk")
        heads = ("f (kHz)", "R (mm)", "F#", "half-angle (deg)", "axial length (mm)", "peak z (mm)")
        frame = ttk.Frame(self.right)
        frame.grid(row=0, column=0, sticky="nsew")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        for c_, h_ in zip(cols, heads):
            self.tree.heading(c_, text=h_)
            self.tree.column(c_, width=110, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.plot = PlotPanel(self.right, figsize=(6.2, 3.6))
        self.plot.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

    def calculate(self):
        W = self.val("W", "Target lateral width") * 1e-3
        dB = self.val("dB", "Width level")
        a = self.val("a", "Aperture radius") * 1e-3
        c = self.val("c", "Sound speed")
        fa, fb, fs = (self.val("fa", "Frequency from"), self.val("fb", "Frequency to"),
                      self.val("fs", "Frequency step"))
        if fb < fa:
            raise ValueError("'Frequency to' must not be smaller than 'Frequency from'.")
        if (fb - fa) / fs > 400:
            raise ValueError("Too many frequencies (max 400). Increase the step.")
        f_values = np.arange(fa, fb + fs / 2, fs) * 1e3
        self.rows = core.design_sweep(c, W, a, dB, f_values)

        self.tree.delete(*self.tree.get_children())
        for r in self.rows:
            if not r["feasible"]:
                self.tree.insert("", "end", values=(f"{r['f']/1e3:.0f}", f"{r['R']*1e3:.1f}",
                                                    "not feasible (R <= a)", "", "", ""))
                continue
            axial = "n/a" if np.isnan(r["axial"]) else f"{r['axial']*1e3:.1f}"
            self.tree.insert("", "end", values=(f"{r['f']/1e3:.0f}", f"{r['R']*1e3:.1f}",
                                                f"{r['f_number']:.2f}", f"{r['half_angle']:.1f}",
                                                axial, f"{r['z_pk']*1e3:.1f}"))

        ok = [r for r in self.rows if r["feasible"] and not np.isnan(r["axial"])]
        fig = self.plot.fig
        fig.clear()
        ax = fig.add_subplot(111)
        if ok:
            fk = [r["f"] / 1e3 for r in ok]
            ax.plot(fk, [r["axial"] * 1e3 for r in ok], "o-", color="tab:blue")
            ax.set_ylabel("Axial length (mm)", color="tab:blue")
            ax2 = ax.twinx()
            ax2.plot(fk, [r["R"] * 1e3 for r in ok], "s--", color="tab:orange")
            ax2.set_ylabel("Required R (mm)", color="tab:orange")
        ax.set_xlabel("Frequency (kHz)")
        ax.set_title(f"-{dB:g} dB lateral width = {W*1e3:g} mm, a = {a*1e3:g} mm")
        ax.grid(True)
        self.plot.draw()

    def save_csv(self):
        if not self.rows:
            messagebox.showinfo("Nothing to save", "Run a calculation first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="design_sweep.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["f_kHz", "R_mm", "F_number", "half_angle_deg", "axial_length_mm", "peak_z_mm"])
            for r in self.rows:
                if r["feasible"]:
                    w.writerow([f"{r['f']/1e3:.0f}", f"{r['R']*1e3:.3f}", f"{r['f_number']:.3f}",
                                f"{r['half_angle']:.2f}", f"{r['axial']*1e3:.3f}", f"{r['z_pk']*1e3:.3f}"])
                else:
                    w.writerow([f"{r['f']/1e3:.0f}", f"{r['R']*1e3:.3f}", "not feasible", "", "", ""])


# --------------------------------------------------------------------------
# Tab 3: band.py
# --------------------------------------------------------------------------
class BandTab(BaseTab):
    def __init__(self, parent):
        super().__init__(parent)
        self.add_inputs("Transducer and scan", [
            ("f0", "Centre frequency f0", 500, "kHz"),
            ("a", "Aperture radius a", 21.5, "mm"),
            ("R", "Radius of curvature R", 30, "mm"),
            ("c", "Sound speed c", 1482, "m/s"),
            ("zmin", "z scan start", 12, "mm"),
            ("zmax", "z scan end", 45, "mm"),
            ("n", "Points in scan", 700, ""),
        ])
        cb = ttk.LabelFrame(self.left, text="Cases: cycles, bandwidth %  (one per line)", padding=8)
        cb.pack(fill="x", pady=(8, 0))
        self.cases = tk.Text(cb, height=5, width=24, font="TkFixedFont")
        self.cases.insert("1.0", "25, 10\n25, 40\n5, 40\n1.5, 40")
        self.cases.pack(fill="x")
        self.normalise = tk.BooleanVar(value=True)
        self.show_cw = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.left, text="Normalise each curve to its own peak",
                        variable=self.normalise).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(self.left, text="Show CW (O'Neil) reference",
                        variable=self.show_cw).pack(anchor="w")
        self.add_buttons([("Calculate", self.run),
                          ("Save results…", lambda: self.save_text(self.out, "burst_bandwidth.txt"))])
        self.add_note("Hann-windowed toneburst times a Gaussian transducer response (a stand-in: "
                      "replace it with the measured response when available). Untick the "
                      "normalisation to see the absolute peak pressure relative to the CW case.")

        self.right.rowconfigure(1, weight=1)
        self.right.columnconfigure(0, weight=1)
        self.out = ResultBox(self.right, height=14)
        self.out.grid(row=0, column=0, sticky="ew")
        self.plot = PlotPanel(self.right)
        self.plot.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

    def parse_cases(self):
        cases = []
        for line in self.cases.get("1.0", "end").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.replace(";", ",").replace("\t", ",").replace(" ", ",").split(",")
            parts = [p for p in parts if p]
            try:
                n, bw = float(parts[0].replace(",", ".")), float(parts[1].replace(",", "."))
            except (ValueError, IndexError):
                raise ValueError(f"Cannot read case '{line}'. Use: cycles, bandwidth %  (e.g. 5, 40).")
            if n <= 0 or not (0 < bw <= 200):
                raise ValueError(f"Case '{line}': cycles must be > 0 and bandwidth between 0 and 200 %.")
            cases.append((n, bw / 100.0))
        if not cases:
            raise ValueError("Enter at least one case.")
        if len(cases) > 8:
            raise ValueError("Maximum 8 cases.")
        return cases

    def calculate(self):
        f0 = self.val("f0", "Centre frequency") * 1e3
        a = self.val("a", "Aperture radius") * 1e-3
        R = self.val("R", "Radius of curvature") * 1e-3
        c = self.val("c", "Sound speed")
        zmin = self.val("zmin", "z scan start") * 1e-3
        zmax = self.val("zmax", "z scan end") * 1e-3
        npts = int(self.val("n", "Points in scan"))
        if zmax <= zmin:
            raise ValueError("z scan end must be larger than z scan start.")
        if not 50 <= npts <= 3000:
            raise ValueError("Points in scan must be between 50 and 3000.")
        cases = self.parse_cases()

        z = np.linspace(zmin, zmax, npts)
        profiles, cw = core.band_profiles(c, f0, a, R, z, cases)

        L = [f"Scan resolution {(z[1]-z[0])*1e3:.3f} mm.  Lengths are contiguous main lobes.",
             f"CW reference (single frequency): peak z = {z[cw.argmax()]*1e3:.1f} mm"]
        L.append("   " + ", ".join(f"-{dB} dB: {self._len(z, cw, dB)}" for dB in (3, 6, 12)))
        L.append("")
        for (n, bw), p in zip(cases, profiles):
            L.append(f"{n:g} cycles, FBW {bw*100:g} %:")
            L.append(f"   peak z = {z[p.argmax()]*1e3:.1f} mm,  peak amplitude = "
                     f"{p.max()/cw.max():.2f} x CW peak")
            L.append("   " + ", ".join(f"-{dB} dB: {self._len(z, p, dB)}" for dB in (3, 6, 12)))
        self.out.set("\n".join(L))

        fig = self.plot.fig
        fig.clear()
        ax = fig.add_subplot(111)
        ref = None if self.normalise.get() else cw.max()
        for (n, bw), p in zip(cases, profiles):
            ax.plot(z * 1e3, 20 * np.log10(p / (p.max() if ref is None else ref)),
                    label=f"{n:g} cycles, FBW {bw*100:g} %")
        if self.show_cw.get():
            ax.plot(z * 1e3, 20 * np.log10(cw / (cw.max())), "k--", lw=1, label="CW reference")
        for dB in (3, 6, 12):
            ax.axhline(-dB, color="gray", ls=":", lw=0.8)
        if ref is None:
            ax.set_ylim(-20, 1)
            ax.set_ylabel("Peak pressure (dB re own peak)")
        else:
            ax.set_ylim(-30, 3)
            ax.set_ylabel("Peak pressure (dB re CW peak)")
        ax.set_xlabel("z from bowl centre (mm)")
        ax.set_title("Axial profile for a burst with finite bandwidth")
        ax.legend(fontsize=8, loc="lower left")
        ax.grid(True)
        self.plot.draw()

    @staticmethod
    def _len(z, p, dB):
        lobe = core.main_lobe(z, p, dB)
        return "n/a" if lobe is None else f"{(lobe[1]-lobe[0])*1e3:.1f} mm"


# --------------------------------------------------------------------------
# Tab 4: margin.py
# --------------------------------------------------------------------------
class MarginTab(BaseTab):
    def __init__(self, parent):
        super().__init__(parent)
        self.add_inputs("Transducer and plate (same unit, mm)", [
            ("R", "Radius of curvature", 30, "mm"),
            ("D", "Aperture diameter", 43, "mm"),
            ("pd", "Plate diameter", 35, "mm"),
            ("ph", "Plate height", 10, "mm"),
        ])
        self.add_buttons([("Calculate", self.run),
                          ("Save results…", lambda: self.save_text(self.out, "rotation_margin.txt"))])
        self.add_note("Plate diameter and height are example values: enter your own plate. "
                      "Critical angle = atan(plate height / plate radius). "
                      "Margin = (90 - critical angle) - aperture edge angle. "
                      "A negative margin means the aperture already exceeds the critical angle.")
        self.right.rowconfigure(0, weight=1)
        self.right.columnconfigure(0, weight=1)
        self.out = ResultBox(self.right, height=14)
        self.out.grid(row=0, column=0, sticky="nsew")

    def calculate(self):
        R = self.val("R", "Radius of curvature")
        D = self.val("D", "Aperture diameter", positive=False)
        pd = self.val("pd", "Plate diameter")
        ph = self.val("ph", "Plate height")
        r = core.rotation_margin(R, D, pd, ph)
        L = [f"For a {pd:g} mm diameter plate with height {ph:g} mm:",
             f"Critical angle: {r['critical_angle']:.3f} degrees",
             "",
             f"Aperture edge angle: {r['aperture_angle']:.3f} degrees",
             f"Sagitta: {r['sagitta']:.3f} mm",
             f"Focus to plate distance: {r['focus_to_plate']:.3f} mm",
             "",
             f"Rotation margin: {r['margin']:.3f} degrees"]
        if r["margin"] < 0:
            L.append("WARNING: negative margin, the aperture already exceeds the critical angle.")
        self.out.set("\n".join(L))


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("1220x800")
        root.minsize(1000, 640)
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.tabs = [
            (FocusTab(nb), "Focal size (focus.py)"),
            (DesignTab(nb), "Design (foc_calc.py)"),
            (BandTab(nb), "Burst & bandwidth (band.py)"),
            (MarginTab(nb), "Rotation margin (margin.py)"),
        ]
        for tab, title in self.tabs:
            nb.add(tab, text=title)
        root.after(200, self.initial_run)

    def initial_run(self):
        for tab, _ in self.tabs:
            tab.run()


def setup_windows():
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TransducerToolkit.App")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def set_icon(root):
    try:
        if sys.platform.startswith("win"):
            root.iconbitmap(resource_path("icon.ico"))
        else:
            img = tk.PhotoImage(file=resource_path("icon.png"))
            root.iconphoto(True, img)
            root._icon_ref = img
    except Exception:
        pass


def main():
    setup_windows()
    root = tk.Tk()
    set_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
