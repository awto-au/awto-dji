clc;clear;close all;
%% Script Info
%This example script loads a single bin file using load_bin.m and prints 
%its spectrogram. Warning! Since the filesize is quite large, this might
%take a long time.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%   AUTHOR: Jaakko Marin        %
%   L-edit: 5.11.20             %
%   email: jaakko.marin@tuni.fi %
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Define Parameters
filepath = 'DJI_inspire_2_2G.bin';
fs = 120e6;     % Use 120e6 for 2.4 GHz and 200e6 for 5.8 GHz
%% Script Begin
iq_data = load_bin(filepath);

%%%% Normalization
iq_data_norm = (iq_data-mean(iq_data))/(sqrt(var(iq_data)));
%%%% 

figure
spectrogram(iq_data_norm,blackman(512),[],[],fs,'centered');
c = colorbar;
c.Label.String = 'Relative spectral power density (dB/Hz)';
title('DJI Inspire 2')
%% Script Complete