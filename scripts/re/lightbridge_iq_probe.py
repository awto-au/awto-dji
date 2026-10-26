#!/usr/bin/env python3
"""Receive-only Lightbridge IQ physical layer probe. No claims of decoding."""
import argparse,json,os
import numpy as np
from scipy import signal

def score_cp(x,lag,cp):
    p=x[:-lag]*np.conj(x[lag:])
    a=np.abs(x[:-lag])**2
    b=np.abs(x[lag:])**2
    w=np.ones(cp,dtype=np.float32)
    # CP normalized correlation in a sliding window
    cross=signal.lfilter(w,[1],p)[cp-1:]
    pa=signal.lfilter(w,[1],a)[cp-1:]
    pb=signal.lfilter(w,[1],b)[cp-1:]
    r=np.abs(cross)/(np.sqrt(pa*pb)+1e-12)
    peaks,_=signal.find_peaks(r,prominence=.12,distance=max(1,lag//2))
    peaks=r[peaks]
    return {"lag":lag,"cp":cp,"p999":round(float(np.quantile(r[::max(1,cp//8)],.999)),4),
            "strong_peaks":int(np.sum(peaks>.65)),
            "largest_peak":round(float(max(peaks)) if len(peaks) else 0.,4)}

def run(fn):
    raw=np.fromfile(fn,dtype="<i2",count=16*1024*1024).reshape(-1,2)
    x=(raw[:,0].astype(np.float32)+1j*raw[:,1].astype(np.float32)) /32768
    x-=np.mean(x)
    fs=120e6
    fc=2440e6
    fft=32768
    psd=np.zeros(fft,dtype=np.float64)
    count=0
    window=np.hanning(fft)
    for start in range(0,len(x)-fft,len(x)//130):
        psd+=np.abs(np.fft.fftshift(np.fft.fft(x[start:start+fft]*window)))**2
        count+=1
    psd/=max(1,count)
    ff=np.fft.fftshift(np.fft.fftfreq(fft,1/fs))
    threshold=np.quantile(psd,.25)
    energies=[]
    for center in np.arange(2404e6,2480e6+1,2e6):
        mask=np.abs(ff-(center-fc))<4.65e6
        energies.append({"center_mhz":round(center/1e6,1),
                         "excess_power":round(float(np.maximum(psd[mask]-threshold,0).sum()),5)})
    energies.sort(key=lambda y:y["excess_power"],reverse=True)
    chosen=energies[0]["center_mhz"]*1e6
    # 120 MS/s to exactly 11.2 MS/s = 7/75
    t=np.arange(len(x),dtype=np.float64)
    x=x*np.exp(-2j*np.pi*((chosen-fc)/fs)*t)
    y=signal.resample_poly(x,7,75).astype(np.complex64)
    y=y[:220000]
    trials=[]
    for label,deltaf in [("standard 11.2MS/s 1024",10937.5),
                         ("patent 9.3kHz",9300),("other 9.765625kHz",9765.625)]:
        lag=int(round(11.2e6/deltaf))
        for cpfrac in (1/16,1/8,1/4):
            p=score_cp(y,lag,int(round(lag*cpfrac)))
            p.update({"hypothesis":label,"cp_ratio":cpfrac})
            trials.append(p)
    return {"input_file":os.path.basename(fn),"recording_rate_sps":int(fs),
            "input_seconds":round(float(len(x)/fs),4),
            "selected_center_mhz":round(chosen/1e6,4),
            "channels_ranked_by_energy":energies[:12],
            "cp_candidates":sorted(trials,key=lambda r:r["p999"],reverse=True),
            "caution":"Frequency-energy maxima may be other transmissions. CP correlation is only a hypothesis test, not proof of a Lightbridge decode."}

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("file")
    z=a.parse_args()
    print(json.dumps(run(z.file),indent=2))
