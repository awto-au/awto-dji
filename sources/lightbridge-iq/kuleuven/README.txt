GENERAL INFORMATION

Drone RF Dataset, Copyright @ Networked Systems, WaveCore, KULeuven, and @ Radio Networks, CISS, Royal Military Academy 
by Sanjoy Basak, Sofie Pollin, and Bart Scheers

contact: sanjoy.basak@mil.be, sanjoy.basak@kuleuven.be

PROJECT INFORMATION

The dataset was developed for a PhD project named: "Drone Detection and Classification using Artificial Intelligence based RF Sensing". The PhD was jointly organized by the Royal Military Academy and KU Leuven.

FILE OVERVIEW

This dataset contains drone RF signals that were recorded within the semi-anechoic chamber at the CISS department of the Royal Military Academy using an Ettus Research USRP X310. A high-speed 10 Gbit Ethernet cable connected the USRP to a computer for data acquisition. We recorded IQ data at a sampling rate of 100 MSps with a center frequency of 2.44 GHz, and an OmniLOG 70600 omnidirectional antenna was employed as the receiving antenna. Drones and remote controllers were positioned at a distance of seven meters from the receiving antenna. IQ samples from the USRP were recorded in binary format, and subsequently, we transformed these binary IQ vectors into complex signal vectors in Matlab, storing them as Mat files (version ‘-v7.3’).

The RF dataset contains RF signals (i.e., remote control (RC) and Video RF signals) from the following drones and remote controllers:

1. Spektrum DX4e remote controllers, 
2. DJI Mini 2 drone + remote controllers, 
3. DJI inspire 2 drone + remote controllers,
4. DJI Matrice 300 drone + remote controllers,
5. Taranis Q X7 remote controllers, 
6. Nine Eagles remote controllers, 
7. WLtoys remote controllers, 
8. Q205 remote controllers, and  
9. SJRC F11 Pro drone + remote controllers.


How to read and process the RF dataset? 

A Matlab script named "signal_visualize.m" is provided with the dataset. The script can be used to read the dataset and plot the spectrogram matrix for the visualization of the RF signals. Please refer to the aforementioned thesis for the pre-processing of RF signals. Additionally, the thesis comprehensively elaborates on the deep learning-based models employed for the detection and classification of drone RF signals.


Publications based on this dataset:

1. S. Basak, S. Rajendran, S. Pollin and B. Scheers, "Autoencoder based framework for drone RF signal classification and novelty detection," 2023 25th International Conference on Advanced Communication Technology (ICACT), Pyeongchang, Korea, Republic of, 2023, pp. 218-225, doi: 10.23919/ICACT56868.2023.10079363.

2. S. Basak, S. Rajendran, S. Pollin and B. Scheers, "Combined RF-Based Drone Detection and Classification," in IEEE Transactions on Cognitive Communications and Networking, vol. 8, no. 1, pp. 111-120, March 2022, doi: 10.1109/TCCN.2021.3099114.












