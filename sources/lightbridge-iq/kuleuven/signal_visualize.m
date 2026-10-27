
clear
close all

NFFT=1024;


Fs=100e6;
f_center=2.44e9;
verbose = 1;


op_samps=100;%ms
op_samps=op_samps/1000;
op_samps=op_samps*Fs;


filenames_all = dir(strcat('Q205/*.mat'));

if isempty(filenames_all)
    disp('no files available in dir!!')
end


for files=1:length(filenames_all)
    disp(files)
    folderprefix=filenames_all(files).folder;
    Fname=filenames_all(files).name;
    Fnameload=strcat(folderprefix,'/',Fname);
    SIGL=data_load(Fnameload);


    figure(1)
    get_spectrogram2(SIGL,Fs,f_center,NFFT);
    pause(0.3)

end



function uhd_samps=data_load(Datafile)
load(Datafile)
end
