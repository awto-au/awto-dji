## Script Info
# This example script loads a single bin file using load_bin.py and prints 
# its spectrogram. Warning! Since the filesize is quite large, this might
# take a long time.

# Import Dependencies
import matplotlib.pyplot as plt
import numpy as np
from load_bin import load_bin

# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# %   AUTHOR: Karel Pärlin         %
# %   L-edit: 9.11.20              %
# %   email: karelparlin@gmail.com %
# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# Define Parameters
filepath = 'DJI_inspire_2_2G.bin'
fs = 120e6     # Use 120e6 for 2.4 GHz and 200e6 for 5.8 GHz
## Script Begin
iq_data = load_bin(filepath)

#### Normalization
iq_data_norm = (iq_data-np.mean(iq_data))/(np.sqrt(np.var(iq_data)))
#### 

plt.figure()
plt.specgram(iq_data_norm,NFFT=512,Fs=fs,window=np.blackman(512),vmin=-155)
cbar = plt.colorbar()
cbar.set_label('Relative spectral power density (dB/Hz)')
plt.xlabel('Time (s)')
plt.ylabel('Frequency (Hz)')
plt.title('DJI Inspire 2')
plt.show()
## Script Complete