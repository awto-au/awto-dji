#!/usr/bin/env python3
"""Blind OFDM cyclic-prefix lag scan on receive-only IQ captures. Not a decode.

Method (no FFT size assumed):
- c(L) = |sum_n y[n+L] conj(y[n])| / sqrt(E_head E_tail), full capture, lags 32..8192.
- OFDM with useful length N and CP length cp peaks at L=N, c(N) ~ cp/(N+cp).
- Null: phase-randomised surrogate (same PSD, no cyclic structure).
- Implied sample rate for a 1024-point FFT: 1024*fs/L_peak.
- Modes: "native" = whole capture at its rate; "scan" = K-subband mix+decimate to 20 MS/s.

Usage: python3 -I scripts/re/analyze_lightbridge_iq.py FILE --fs 120e6 --mode scan
"""
import argparse
import os
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal

HYPOTHESES = [
    ("WiMAX 1024 @11.2MS/s (10.9375 kHz)", 10937.5),
    ("patent 9.3 kHz", 9300.0),
    ("1024 @10MS/s (9.765625 kHz)", 9765.625),
]


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, check=True, cwd=Path(__file__).resolve().parent)
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, OSError):
        return Path(__file__).resolve().parents[2]


class Log:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(path, "w")

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        self.f.write(s + "\n")
        self.f.flush()


def load(path, nsamp, dtype):
    if dtype == "int16":
        raw = np.fromfile(path, dtype="<i2", count=2 * nsamp).astype(np.float32)
    else:  # interleaved little-endian float16 (Genesys UAV-Sigmf-float16 bursts)
        raw = np.fromfile(path, dtype="<f2", count=2 * nsamp).astype(np.float32)
    raw = raw[: (raw.size // 2) * 2].reshape(-1, 2)
    x = (raw[:, 0] + 1j * raw[:, 1]).astype(np.complex64)
    return x - x.mean()


def occupied_bw(x, fs):
    f, p = signal.welch(x, fs=fs, nperseg=4096, return_onesided=False)
    f = np.fft.fftshift(f)
    p = np.fft.fftshift(p)
    cum = np.cumsum(p) / p.sum()
    lo = f[np.searchsorted(cum, 0.005)]
    hi = f[np.searchsorted(cum, 0.995)]
    return f[np.argmax(p)], hi - lo


def norm_corr(y, lags):
    m = y.size
    nfft = 1 << int(np.ceil(np.log2(2 * m)))
    r = np.fft.ifft(np.abs(np.fft.fft(y, nfft)) ** 2)
    p = np.abs(y) ** 2
    cs = np.concatenate([[0.0], np.cumsum(p, dtype=np.float64)])
    head = cs[m - lags]
    tail = cs[m] - cs[lags]
    return np.abs(r[lags]) / np.sqrt(head * tail + 1e-30)


def surrogate(y, rng):
    # Null = Gaussian noise with the PSD smoothed to nperseg=256 bins. Phase-randomising
    # the full FFT would keep |Y(f)|^2 and so keep every lag correlation (not a null).
    m = y.size
    fw, pw = signal.welch(y, nperseg=256, return_onesided=False)
    amp = np.sqrt(np.interp(np.fft.fftshift(np.fft.fftfreq(m)), np.fft.fftshift(fw), np.fft.fftshift(pw)))
    g = rng.standard_normal(m) + 1j * rng.standard_normal(m)
    return np.fft.ifft(np.fft.fft(g) * np.fft.ifftshift(amp)).astype(np.complex64)


def scan_one(y, fs, label, log, rng):
    lags = np.arange(32, min(8192, y.size // 8))
    c = norm_corr(y, lags)
    cs_ = norm_corr(surrogate(y, rng), lags)
    med = np.median(c)
    sig = 1.4826 * np.median(np.abs(c - med))
    i = int(np.argmax(c))
    L = int(lags[i])
    z = (c[i] - med) / sig
    log(f"  [{label}] fs={fs/1e6:.4g} MS/s n={y.size}  peak lag L={L} "
        f"c={c[i]:.4f} z={z:.1f}  surrogate max c={cs_.max():.4f} (lag {int(lags[np.argmax(cs_)])})")
    log(f"    implied spacing fs/L = {fs/L:.1f} Hz; implied CP/N = c/(1-c) = {c[i]/(1-c[i]):.3f}; "
        f"if N=1024: fs_implied = {1024*fs/L/1e6:.3f} MS/s")
    for name, df in HYPOTHESES:
        Lh = fs / df
        k = np.abs(lags - Lh) <= 1.5
        if k.any():
            j = int(np.argmax(np.where(k, c, -1)))
            log(f"    {name}: expected lag {Lh:.2f}, best c within +-1.5 = {c[j]:.4f} at lag {lags[j]} "
                f"(z={(c[j]-med)/sig:.1f})")
    return {"label": label, "fs": fs, "peak_lag": L, "c": float(c[i]), "z": float(z),
            "surrogate_max_c": float(cs_.max())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--fs", type=float, required=True, help="native sample rate, Hz")
    ap.add_argument("--mode", choices=["native", "scan"], default="native")
    ap.add_argument("--dtype", choices=["int16", "f16"], default="int16",
                    help="interleaved I/Q sample type on disk")
    ap.add_argument("--nsamp", type=int, default=1 << 24, help="complex samples read from file start")
    ap.add_argument("--subband-step", type=float, default=10e6, help="scan: subband centre step, Hz")
    ap.add_argument("--span", type=float, default=110e6, help="scan: total span to tile, Hz")
    a = ap.parse_args()

    stem = Path(a.file).stem
    log = Log(repo_root() / "tmp" / "logs" / f"analyze_lightbridge_iq_{stem}_{a.mode}.log")
    rng = np.random.default_rng(1)
    x = load(a.file, a.nsamp, a.dtype)
    log(f"file={a.file} native_fs={a.fs/1e6:.4g} MS/s read={x.size} samples ({x.size/a.fs*1e3:.1f} ms)")
    log(f"  rms={np.sqrt(np.mean(np.abs(x)**2)):.4g} max|x|={np.abs(x).max():.4g}")
    fpk, bw = occupied_bw(x, a.fs)
    log(f"  whole-capture peak PSD at {fpk/1e6:+.3f} MHz from centre; 99% occupied BW = {bw/1e6:.3f} MHz")

    results = []
    if a.mode == "native":
        results.append(scan_one(x, a.fs, "native", log, rng))
    else:
        dec = int(round(a.fs / 20e6))
        fs_b = a.fs / dec
        offs = np.arange(-a.span / 2 + 5e6, a.span / 2, a.subband_step)
        t = np.arange(x.size)
        for off in offs:
            y = x * np.exp(-2j * np.pi * off / a.fs * t).astype(np.complex64)
            y = signal.resample_poly(y, 1, dec).astype(np.complex64)
            results.append(scan_one(y, fs_b, f"sub {off/1e6:+.0f} MHz", log, rng))
    results.sort(key=lambda r: r["z"], reverse=True)
    log("RANKED by z:")
    for r in results[:5]:
        log(f"  {r['label']}: L={r['peak_lag']} c={r['c']:.4f} z={r['z']:.1f}")


if __name__ == "__main__":
    main()
