#!/usr/bin/env python3
"""Receive-only OFDM parameter measurement on DJI IQ captures (awto-dji#71). Not a decode.

Stages:
- occupancy: spectrogram -> active time/frequency regions (bursts, hopping), PNG in tmp/.
- burst:     per burst, mix to its centre, low-pass to its bandwidth.
- Tu:        useful symbol length from CP lag correlation, fractional (parabolic) peak.
- T, CP:     symbol period from the cyclic spectrum of the lag-Tu product; CP = T - Tu.
- carriers:  CP-stripped FFTs at the folded symbol timing -> occupied/null/pilot-like bins.

Usage: python3 -I scripts/re/lightbridge_ofdm_params.py FILE --fs 120e6 [--dtype int16|f16]
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal


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


def load(path, nsamp, dtype, offset):
    np_dt = "<i2" if dtype == "int16" else "<f2"
    raw = np.fromfile(path, dtype=np_dt, count=2 * nsamp, offset=offset * 4)  # 2 x 2-byte per sample
    raw = raw[: (raw.size // 2) * 2].astype(np.float32).reshape(-1, 2)
    x = (raw[:, 0] + 1j * raw[:, 1]).astype(np.complex64)
    return x - x.mean()


# ---------------------------------------------------------------- occupancy
def occupancy(x, fs, log, png, nfft=1024, hop_us=20.0):
    """Spectrogram in dB; active cell = > noise floor + 10 dB. Returns (t, f, S_db, active)."""
    hop = max(1, int(fs * hop_us * 1e-6))
    f, t, S = signal.spectrogram(x, fs=fs, nperseg=nfft, noverlap=nfft - hop,
                                 return_onesided=False, mode="psd", window="hann")
    f = np.fft.fftshift(f)
    S = np.fft.fftshift(S, axes=0)
    S_db = 10 * np.log10(S + 1e-30)
    floor = np.median(S_db)
    active = S_db > floor + 10.0
    log(f"occupancy: {S.shape[1]} frames x {S.shape[0]} bins, bin={fs/nfft/1e3:.1f} kHz, "
        f"hop={hop/fs*1e6:.1f} us, floor={floor:.1f} dB")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.imshow(S_db, aspect="auto", origin="lower", cmap="viridis",
                  extent=[t[0] * 1e3, t[-1] * 1e3, f[0] / 1e6, f[-1] / 1e6],
                  vmin=floor, vmax=floor + 40)
        ax.set_xlabel("time (ms)")
        ax.set_ylabel("offset from capture centre (MHz)")
        ax.set_title(png.stem)
        fig.tight_layout()
        fig.savefig(png, dpi=110)
        plt.close(fig)
        log(f"  spectrogram -> {png}")
    except ImportError:
        log("  matplotlib missing, no PNG")
    return t, f, S_db, active, floor


def find_bursts(t, f, S_db, active, fs, log, min_bins=8, min_frames=3):
    """Group active frames into bursts; each burst gets its band from the mean spectrum."""
    frame_on = active.sum(axis=0) >= min_bins
    edges = np.flatnonzero(np.diff(np.concatenate([[0], frame_on.astype(int), [0]])))
    starts, stops = edges[::2], edges[1::2]
    dt = t[1] - t[0]
    bursts = []
    for s, e in zip(starts, stops):
        if e - s < min_frames:
            continue
        prof = S_db[:, s:e].mean(axis=1)
        pk = prof.max()
        band = np.flatnonzero(prof > pk - 20.0)
        # largest contiguous run around the peak
        runs = np.split(band, np.flatnonzero(np.diff(band) > 2) + 1)
        run = max(runs, key=lambda r: prof[r].sum())
        lo, hi = f[run[0]], f[run[-1]]
        bursts.append({"t0": float(t[s] - dt / 2), "t1": float(t[e - 1] + dt / 2),
                       "f_lo": float(lo), "f_hi": float(hi), "fc": float((lo + hi) / 2),
                       "bw": float(hi - lo), "peak_db": float(pk)})
    log(f"bursts: {len(bursts)}")
    return bursts


def summarise_bursts(bursts, log):
    if not bursts:
        return
    dur = np.array([b["t1"] - b["t0"] for b in bursts]) * 1e3
    fc = np.array([b["fc"] for b in bursts]) / 1e6
    bw = np.array([b["bw"] for b in bursts]) / 1e6
    t0 = np.array([b["t0"] for b in bursts]) * 1e3
    log(f"  duration ms: min={dur.min():.3f} med={np.median(dur):.3f} max={dur.max():.3f}")
    log(f"  bandwidth MHz (-20 dB): min={bw.min():.2f} med={np.median(bw):.2f} max={bw.max():.2f}")
    cents, counts = np.unique(np.round(fc, 0), return_counts=True)
    log("  centre MHz histogram: " + ", ".join(f"{c:+.0f}:{n}" for c, n in zip(cents, counts)))
    if len(t0) > 2:
        d = np.diff(t0)
        log(f"  start-to-start ms: min={d.min():.3f} med={np.median(d):.3f} max={d.max():.3f}")
    for b in bursts:
        log(f"    t={b['t0']*1e3:8.3f}..{b['t1']*1e3:8.3f} ms  fc={b['fc']/1e6:+7.2f} MHz  "
            f"bw={b['bw']/1e6:5.2f} MHz  pk={b['peak_db']:.1f} dB")


# ---------------------------------------------------------------- per-burst OFDM
def channelise(x, fs, fc, bw, t0, t1):
    i0, i1 = max(0, int(t0 * fs)), min(x.size, int(t1 * fs))
    y = x[i0:i1] * np.exp(-2j * np.pi * fc / fs * np.arange(i0, i1)).astype(np.complex64)
    taps = signal.firwin(255, min(0.98, 0.6 * bw / (fs / 2) + 0.02))
    return signal.lfilter(taps, 1.0, y).astype(np.complex64)[127:]


def lag_corr(y, lags):
    m = y.size
    nfft = 1 << int(np.ceil(np.log2(2 * m)))
    r = np.fft.ifft(np.abs(np.fft.fft(y, nfft)) ** 2)
    p = np.abs(y) ** 2
    cs = np.concatenate([[0.0], np.cumsum(p, dtype=np.float64)])
    return np.abs(r[lags]) / np.sqrt(cs[m - lags] * (cs[m] - cs[lags]) + 1e-30), r[lags]


def useful_len(y, fs, lo_hz=3e3, hi_hz=40e3):
    """Fractional lag of the strongest CP correlation, plus CFO from its phase."""
    lags = np.arange(int(fs / hi_hz), min(int(fs / lo_hz), y.size // 4))
    c, r = lag_corr(y, lags)
    i = int(np.argmax(c))
    med = np.median(c)
    sig = 1.4826 * np.median(np.abs(c - med)) + 1e-12
    if 0 < i < c.size - 1:
        a, b, d = c[i - 1], c[i], c[i + 1]
        frac = 0.5 * (a - d) / (a - 2 * b + d)
    else:
        frac = 0.0
    L = lags[i] + frac
    cfo = -np.angle(r[i]) * fs / (2 * np.pi * lags[i])  # residual within +-df/2
    return float(L), float(c[i]), float((c[i] - med) / sig), float(cfo)


def symbol_period(y, Lu, fs):
    """Cyclic spectrum of Re{y[n+Lu] y*[n]} (phase-aligned): line at fs/T, T in (Lu, 1.5 Lu)."""
    Li = int(round(Lu))
    p = y[Li:] * np.conj(y[:-Li])
    p = np.real(p * np.exp(-1j * np.angle(p.sum())))
    p = p - p.mean()
    nfft = 1 << int(np.ceil(np.log2(p.size * 4)))
    P = np.abs(np.fft.rfft(p, nfft))
    fr = np.fft.rfftfreq(nfft, 1 / fs)
    k = (fr > fs / (1.5 * Lu)) & (fr < fs / (1.01 * Lu))
    j = np.flatnonzero(k)[np.argmax(P[k])]
    if 0 < j < P.size - 1:
        a, b, d = P[j - 1], P[j], P[j + 1]
        jf = j + 0.5 * (a - d) / (a - 2 * b + d)
    else:
        jf = j
    f_sym = jf * fs / nfft
    noise = np.median(P[k]) + 1e-12
    return fs / f_sym, float(P[j] / noise), p


def fold_cp(p, T, Lu):
    """Fold the aligned lag product at period T: CP shows as a plateau of width ~Ncp."""
    nb = int(round(T))
    ph = (np.arange(p.size) % T).astype(int)
    ph[ph >= nb] = nb - 1
    prof = np.bincount(ph, weights=p, minlength=nb) / np.maximum(np.bincount(ph, minlength=nb), 1)
    thr = prof.min() + 0.5 * (prof.max() - prof.min())
    on = prof > thr
    # circular plateau width and its start (= symbol start)
    on2 = np.concatenate([on, on])
    best, best_start, run, start = 0, 0, 0, 0
    for i, v in enumerate(on2):
        if v:
            if run == 0:
                start = i
            run += 1
            if run > best:
                best, best_start = run, start
        else:
            run = 0
    return int(min(best, nb)), int(best_start % nb), prof


def carrier_map(y, fs, Lu, T, sym_start, cfo, max_syms=400):
    """Resample so one useful symbol = 1024 samples, strip CP, FFT, per-bin statistics."""
    n = np.arange(y.size)
    y = y * np.exp(-2j * np.pi * cfo / fs * n).astype(np.complex64)
    N = 1024
    scale = N / Lu
    starts = sym_start + np.arange(0, (y.size - sym_start - T) / T) * T
    starts = starts[:max_syms]
    if starts.size < 8:
        return None
    cp = T - Lu
    X = []
    for s in starts:
        t_idx = s + cp + np.arange(N) / scale  # fractional sample positions of the useful part
        i0 = int(np.floor(t_idx[0]))
        seg = y[i0: i0 + int(np.ceil(Lu)) + 3]
        if seg.size < int(np.ceil(Lu)) + 3:
            break
        xs = np.interp(t_idx - i0, np.arange(seg.size), seg.real) + \
            1j * np.interp(t_idx - i0, np.arange(seg.size), seg.imag)
        X.append(np.fft.fftshift(np.fft.fft(xs)))
    X = np.array(X)
    pw = np.mean(np.abs(X) ** 2, axis=0)
    pw_db = 10 * np.log10(pw + 1e-30)
    ref = np.percentile(pw_db, 90)
    occ = pw_db > ref - 10.0
    # integer carrier offset: re-centre so the occupied span is symmetric about bin N/2
    idx = np.flatnonzero(occ)
    shift = int(round((idx[0] + idx[-1]) / 2)) - N // 2
    X, pw_db, occ = np.roll(X, -shift, axis=1), np.roll(pw_db, -shift), np.roll(occ, -shift)
    # pilot test on short windows: sampling-clock drift rotates bins over a long burst
    win = 8
    coh1, coh2 = np.zeros(N), np.zeros(N)
    nw = X.shape[0] // win
    for w in range(nw):
        Xw = X[w * win:(w + 1) * win]
        cpe = np.angle(np.sum(Xw[:, occ] * np.conj(Xw[0:1, occ]), axis=1))
        Xw = Xw * np.exp(-1j * cpe)[:, None]
        coh1 += np.abs(Xw.mean(axis=0)) / (np.abs(Xw).mean(axis=0) + 1e-30)
        coh2 += np.abs((Xw ** 2).mean(axis=0)) / ((np.abs(Xw) ** 2).mean(axis=0) + 1e-30)
    coh1, coh2 = coh1 / nw, coh2 / nw
    return {"nsym": int(X.shape[0]), "pw_db": pw_db, "occ": occ, "coh1": coh1, "coh2": coh2,
            "int_shift": shift, "win": win, "X": X}


def pilot_search(cm, log, grid=9, max_lag=12):
    """Pilot residue per symbol: BPSK^2 coherence of X[m,k] X*[m+lag,k] averaged over k = q mod grid.

    Pilots on residue q in both symbols m and m+lag -> high value; data -> ~1/sqrt(#bins).
    Returns the dominant residue per symbol and the lag at which the pattern repeats.
    """
    X, occ = cm["X"], cm["occ"]
    N = occ.size
    k = np.arange(N) - N // 2
    res = (k - k[occ][0]) % grid
    M = X.shape[0]
    # per-symbol residue power: boosted pilots show directly, no pairing needed
    pw = np.abs(X) ** 2
    rp = np.array([[pw[m, occ & (res == q)].mean() for q in range(grid)] for m in range(M)])
    rp_db = 10 * np.log10(rp / np.median(rp, axis=1, keepdims=True))
    q_pow = rp_db.argmax(axis=1)
    log(f"    residue (k mod {grid}) with max power per symbol, first 24: {q_pow[:24].tolist()} "
        f"(peak excess median {np.median(rp_db.max(axis=1)):+.2f} dB)")
    coh_by_lag = {}
    for lag in range(1, max_lag + 1):
        d = X[lag:] * np.conj(X[:-lag])
        cpe = np.angle(np.sum(d[:, occ] ** 2, axis=1)) / 2
        d2 = (d * np.exp(-1j * cpe)[:, None]) ** 2
        tab = np.array([[np.abs(d2[m, occ & (res == q)].mean()) / (np.abs(d2[m, occ & (res == q)]).mean() + 1e-30)
                         for q in range(grid)] for m in range(d2.shape[0])])
        coh_by_lag[lag] = (tab.max(axis=1), tab.argmax(axis=1))
        log(f"    lag {lag:2d}: median best-residue coh {np.median(tab.max(axis=1)):.2f} "
            f"(other residues median {np.median(np.sort(tab, axis=1)[:, :-1]):.2f})")
    lag_best = max(coh_by_lag, key=lambda L: np.median(coh_by_lag[L][0]))
    q_seq = coh_by_lag[lag_best][1]
    log(f"    pattern lag {lag_best}: pilot residue per symbol, first 24: {q_seq[:24].tolist()}")
    steps = np.diff(q_seq) % grid
    vals, cnts = np.unique(steps, return_counts=True)
    log(f"    residue step symbol->symbol (count:step): {', '.join(f'{c}:{v}' for c, v in sorted(zip(cnts, vals), reverse=True)[:4])}")
    return {"grid": grid, "lag": int(lag_best), "q_seq": q_seq.tolist(), "q_pow": q_pow[:48].tolist(),
            "res": res}


def constellation(cm, pil, log, png, max_dist=4):
    """Data bins referenced to the nearest same-symbol pilot: r = X_d X_p* / |X_p|^2.

    Pilot +-1 leaves a sign ambiguity, harmless for square QAM. Smoothed-channel variants
    (static over burst; per-symbol sqrt-interpolated) scored worse on the 4th-power test.
    """
    X, occ, res = cm["X"], cm["occ"], pil["res"]
    q_seq = np.array(pil["q_seq"])
    N = occ.size
    rs = []
    for m in range(min(X.shape[0], q_seq.size)):
        pmask = occ & (res == q_seq[m])
        pk = np.flatnonzero(pmask)
        dk = np.flatnonzero(occ & ~pmask & (np.arange(N) != N // 2))
        j = np.clip(np.searchsorted(pk, dk), 1, pk.size - 1)
        near = np.where(np.abs(pk[j] - dk) < np.abs(pk[j - 1] - dk), pk[j], pk[j - 1])
        ok = np.abs(near - dk) <= max_dist
        xp = X[m, near[ok]]
        rs.append(X[m, dk[ok]] * np.conj(xp) / (np.abs(xp) ** 2 + 1e-30))
    r = np.concatenate(rs)
    r = r / np.sqrt(np.mean(np.abs(r) ** 2))
    # robust: drop worst 1% (deep-fade pilots blow up the ratio)
    r = r[np.abs(r) < np.percentile(np.abs(r), 99)]
    r = r / np.sqrt(np.mean(np.abs(r) ** 2))
    k4 = np.mean(np.abs(r) ** 4)
    # 4th-power coherence: pilot +-1 drops out; square QAM -> |E r^4|/E|r|^4 of 1.0 (QPSK),
    # 0.47 (16QAM), 0.38 (64QAM); Gaussian / superposed streams -> ~0
    m4 = np.abs(np.mean(r ** 4)) / np.mean(np.abs(r) ** 4)
    log(f"    constellation: {r.size} data cells; E|r|^4/E|r|^2^2 = {k4:.3f} "
        f"(ideal QPSK 1.00, 16QAM 1.32, 64QAM 1.38; Gaussian 2.0); "
        f"|E r^4|/E|r|^4 = {m4:.3f} (QPSK 1.0, 16QAM 0.47, 64QAM 0.38, Gaussian 0)")
    # quadrant fold (sign ambiguity + QAM symmetry) then 1-D histogram of |Re|, |Im|
    a = np.concatenate([np.abs(r.real), np.abs(r.imag)])
    h, e = np.histogram(a, bins=60, range=(0, 2))
    pk = signal.find_peaks(h, prominence=h.max() * 0.08)[0]
    log(f"    |I|,|Q| histogram peaks at {[round(float((e[i] + e[i + 1]) / 2), 2) for i in pk]} "
        f"(QPSK ~0.71; 16QAM ~0.32,0.95; 64QAM ~0.15,0.46,0.77,1.08)")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(11, 5))
        ax[0].hist2d(r.real, r.imag, bins=200, range=[[-2, 2], [-2, 2]], cmap="magma")
        ax[0].set_aspect("equal")
        ax[0].set_title("data / nearest pilot")
        ax[1].bar((e[:-1] + e[1:]) / 2, h, width=e[1] - e[0])
        ax[1].set_title("|I| and |Q|")
        fig.tight_layout()
        fig.savefig(png, dpi=100)
        plt.close(fig)
        log(f"    constellation -> {png}")
    except ImportError:
        pass
    return {"kurt4": float(k4), "m4_coh": float(m4), "iq_peaks": [float((e[i] + e[i + 1]) / 2) for i in pk]}


def describe_carriers(cm, log):
    occ = cm["occ"]
    k = np.arange(occ.size) - occ.size // 2
    idx = np.flatnonzero(occ)
    log(f"    carriers (1024-bin grid, {cm['nsym']} symbols, re-centred by {cm['int_shift']:+d} bins): "
        f"occupied={occ.sum()} span k=[{k[idx[0]]},{k[idx[-1]]}] -> {k[idx[-1]]-k[idx[0]]+1} bins incl. nulls")
    dc = cm["pw_db"][occ.size // 2] - np.median(cm["pw_db"][occ])
    log(f"    DC bin relative to occupied median: {dc:+.1f} dB")
    # 802.16e DL preamble: every 3rd subcarrier -> one residue mod 3 carries ~all the power
    for m in range(min(3, cm["X"].shape[0])):
        p = np.abs(cm["X"][m]) ** 2
        r3 = [p[occ & ((k - k[idx[0]]) % 3 == q)].sum() for q in range(3)]
        log(f"    symbol {m}: power share by k mod 3 = {np.round(np.array(r3) / sum(r3), 2).tolist()} "
            f"(WiMAX preamble ~[1,0,0] in some order; normal symbol ~0.33 each)")
    inner = idx[(idx > idx[0]) & (idx < idx[-1])]
    holes = np.setdiff1d(np.arange(idx[0], idx[-1] + 1), idx)
    log(f"    nulls inside span: {holes.size} at k={list(k[holes][:16])}{'...' if holes.size > 16 else ''}")
    for name, key in (("coherent (fixed-value pilot-like)", "coh1"), ("BPSK-squared coherent", "coh2")):
        v = cm[key][occ]
        hi = idx[v > 0.6]
        log(f"    {name}, {cm['win']}-symbol windows: {hi.size} bins >0.6 (median {np.median(v):.2f}, "
            f"p99 {np.percentile(v, 99):.2f}); "
            f"k={list(k[hi][:24])}{'...' if hi.size > 24 else ''}")
        if hi.size > 2:
            d = np.diff(k[hi])
            vals, cnts = np.unique(d, return_counts=True)
            top = sorted(zip(cnts, vals), reverse=True)[:4]
            log(f"      spacing histogram (count:delta): {', '.join(f'{c}:{v}' for c, v in top)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--fs", type=float, required=True, help="native sample rate, Hz")
    ap.add_argument("--dtype", choices=["int16", "f16"], default="int16")
    ap.add_argument("--nsamp", type=int, default=1 << 25, help="complex samples to read")
    ap.add_argument("--offset", type=int, default=0, help="complex samples to skip")
    ap.add_argument("--max-bursts", type=int, default=12, help="bursts to run OFDM stages on")
    ap.add_argument("--min-burst-ms", type=float, default=0.3, help="skip shorter bursts (too few symbols)")
    ap.add_argument("--pilots", action="store_true", help="search for symbol-dependent pilot patterns")
    ap.add_argument("--min-bw-mhz", type=float, default=0.0, help="only bursts at least this wide")
    ap.add_argument("--max-bw-mhz", type=float, default=1e9, help="only bursts at most this wide")
    a = ap.parse_args()

    stem = Path(a.file).stem
    if a.max_bw_mhz < 1e9:
        stem += f"_bw{a.min_bw_mhz:g}-{a.max_bw_mhz:g}"
    out = repo_root() / "tmp"
    log = Log(out / "logs" / f"lightbridge_ofdm_params_{stem}.log")
    x = load(a.file, a.nsamp, a.dtype, a.offset)
    log(f"file={a.file} fs={a.fs/1e6:.4g} MS/s samples={x.size} ({x.size/a.fs*1e3:.1f} ms)")
    if x.size < 1 << 16:
        raise SystemExit(f"capture too short: {x.size} samples")

    t, f, S_db, active, floor = occupancy(x, a.fs, log, out / f"lightbridge_ofdm_{stem}.png")
    bursts = find_bursts(t, f, S_db, active, a.fs, log)
    summarise_bursts(bursts, log)

    results = []
    cand = [b for b in bursts if (b["t1"] - b["t0"]) * 1e3 >= a.min_burst_ms
            and a.min_bw_mhz <= b["bw"] / 1e6 <= a.max_bw_mhz]
    cand.sort(key=lambda b: b["bw"] * (b["t1"] - b["t0"]), reverse=True)  # time-bandwidth first
    for b in cand[: a.max_bursts]:
        y = channelise(x, a.fs, b["fc"], b["bw"], b["t0"], b["t1"])
        if y.size < 4 * a.fs / 3e3:  # useful_len scans lags up to fs/3 kHz, needs ~4x that
            continue
        Lu, c, z, cfo = useful_len(y, a.fs)
        T, snr_T, p = symbol_period(y, Lu, a.fs)
        ncp_fold, s0, _ = fold_cp(p, T, Lu)
        df = a.fs / Lu
        r = {"t0_ms": b["t0"] * 1e3, "fc_mhz": b["fc"] / 1e6, "bw_mhz": b["bw"] / 1e6,
             "dur_ms": (b["t1"] - b["t0"]) * 1e3, "Lu": Lu, "df_hz": df, "c": c, "z": z,
             "T": T, "T_snr": snr_T, "cp_samples": T - Lu, "cp_ratio": (T - Lu) / Lu,
             "cp_fold_samples": ncp_fold, "Tsym_us": T / a.fs * 1e6, "cfo_hz": cfo,
             "carriers_in_bw": b["bw"] / df}
        log(f"  burst t={r['t0_ms']:.3f} ms fc={r['fc_mhz']:+.2f} MHz bw={r['bw_mhz']:.2f} dur={r['dur_ms']:.2f} ms")
        log(f"    Tu={Lu:.2f} samp -> df={df:.1f} Hz (c={c:.3f} z={z:.1f}); T={T:.2f} samp "
            f"(line {snr_T:.1f}x median) -> CP={T-Lu:.1f} samp = {r['cp_ratio']:.4f} Tu; "
            f"fold plateau={ncp_fold} samp; Tsym={r['Tsym_us']:.2f} us; CFO residual={cfo:+.0f} Hz")
        if z > 8 and snr_T > 8:
            cm = carrier_map(y, a.fs, Lu, T, s0, cfo)
            if cm is not None:
                describe_carriers(cm, log)
                if a.pilots:
                    pil = pilot_search(cm, log)
                    r["constellation"] = constellation(
                        cm, pil, log, out / f"lightbridge_const_{stem}_{b['t0']*1e3:.0f}ms.png")
                    pil.pop("res")
                    r["pilots"] = pil
                r["occupied_bins_1024"] = int(cm["occ"].sum())
                r["fc_refined_mhz"] = (b["fc"] + cm["int_shift"] * df + cfo) / 1e6
        results.append(r)

    if results:
        good = [r for r in results if r["z"] > 8 and r["T_snr"] > 8]
        log(f"SUMMARY over {len(good)}/{len(results)} bursts passing z>8 and T-line>8:")
        for key in ("df_hz", "cp_ratio", "Tsym_us", "occupied_bins_1024"):
            v = np.array([r[key] for r in good if key in r], dtype=float)
            if v.size:
                log(f"  {key}: mean={v.mean():.4f} std={v.std(ddof=1) if v.size > 1 else 0:.4f} "
                    f"min={v.min():.4f} max={v.max():.4f} n={v.size}")
    (out / f"lightbridge_ofdm_{stem}.json").write_text(json.dumps(
        {"file": a.file, "fs": a.fs, "bursts": bursts, "ofdm": results}, indent=1))
    log(f"json -> {out / f'lightbridge_ofdm_{stem}.json'}")


if __name__ == "__main__":
    main()
