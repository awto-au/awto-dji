function [SpectrumMatrix_amp]= get_spectrogram2(rx_signal,Fs,fc,NFFT)

y=rx_signal;
len=length(rx_signal);
N=floor(len/NFFT);
% w=hamming(NFFT);        %Hamming window
w=hanning(NFFT);        %Hamming window
wmat=repmat(w,1,N);  %NFFT by N matrix of hamming windows 
IQMatrix=reshape(y(1:N*NFFT),NFFT,N); %time vectors along the columns
SpectrumMatrix=fft(IQMatrix.*wmat); %fft takes DFT along the columns
SpectrumMatrix2=fftshift(SpectrumMatrix,1); %fftshift along the columns

SpectrumMatrix_amp2=abs(SpectrumMatrix2);
SpectrumMatrix_amp=transpose(SpectrumMatrix_amp2);

N2=round(len/NFFT);
tot_time=len/Fs *1000;%to ms
time_vector=linspace(1,tot_time,N2);

FreqVector=-Fs/2+fc:Fs/NFFT:Fs/2-1+fc;


SpectrumMatrix_amp = 10*log10(SpectrumMatrix_amp);
SpectrumMatrix_amp(isnan(SpectrumMatrix_amp))=min(SpectrumMatrix_amp(:));
SpectrumMatrix_amp = (SpectrumMatrix_amp-mean(SpectrumMatrix_amp(:)))/std(SpectrumMatrix_amp(:));
SpectrumMatrix_amp(isnan(SpectrumMatrix_amp))=min(SpectrumMatrix_amp(:));

imagesc(FreqVector,time_vector,SpectrumMatrix_amp)

xlabel('Frequency (GHz)')
ylabel('Time (ms)')

end
