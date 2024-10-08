import os, sys, shutil, glob
import argparse
import math
import numpy as np
import ROOT
import pickle
import matplotlib.pyplot as plt
import scipy
import scipy.optimize as opt
from array import array
from ROOT import gStyle, gPad, kRed, TMath
import csv

# load the RNO-G library
ROOT.gSystem.Load(os.environ.get('RNO_G_INSTALL_DIR')+"/lib/libmattak.so")

# make sure we have enough arguments to proceed
parser = argparse.ArgumentParser(description='daqstatus example')
parser.add_argument('--file', dest='file', required=True)
args = parser.parse_args()
filename = args.file

#voltage calibration coeffs

cal_path = "/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/volCalConsts_pol9_s23_1697181551-1697183024.root"
#cal_path = "/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/volCalConsts_pol9_s11_1719015822-1719017482.root"
fIn = ROOT.TFile.Open(filename)
combinedTree = fIn.Get("combined")


volCalib = ROOT.mattak.VoltageCalibration()
volCalib.readFitCoeffsFromFile(cal_path)


d = ROOT.mattak.DAQStatus()
wf = ROOT.mattak.Waveforms()
hdr = ROOT.mattak.Header()

combinedTree.SetBranchAddress("daqstatus", ROOT.AddressOf(d))
combinedTree.SetBranchAddress("waveforms", ROOT.AddressOf(wf))
combinedTree.SetBranchAddress("header", ROOT.AddressOf(hdr))

num_events = combinedTree.GetEntries()

att_counts = {} #number of triggered events in each attenuation bin 
binned_times = {} #timestamps correponding to each attenuation bin 

for att in np.arange(0,32, 0.5):
    att_counts[att] = 0
    binned_times[att] = []

for event in range(num_events):
    combinedTree.GetEntry(event)

    sysclk = hdr.sysclk
    sysclk_last_pps = hdr.sysclk_last_pps
    sys_diff = (sysclk - sysclk_last_pps)%(2**(32))

    atten = d.calinfo.attenuation
    time = d.readout_time_lt

    binned_times[atten].append(time)

    #cut on cal pulser 
    if (sys_diff <= 200*10**(3)):
        att_counts[atten] += 1


#time spent at each attenuation
diff_time = {}
diffs = []
for att in binned_times:
    times = binned_times[att]
    if times != []:
        min_time = np.min(times)
        max_time = np.max(times)
        diff = max_time - min_time
        diffs.append(diff)
        diff_time[att] = diff

trig_eff = {}
trig_err = {}
a_counts = []
wilson_err_hi = {}
wilson_err_lo = {}

#calculating trigger efficiency and error in each attenuation bin

for a in att_counts:
    diff = diff_time[a]
    #diff = 100
    trig_eff[a] = att_counts[a]/diff
    trig_err[a] = np.sqrt(att_counts[a])/diff
    wilson_bound_hi = ROOT.TEfficiency.Wilson(diff, att_counts[a], 0.68, True)
    wilson_bound_lo = ROOT.TEfficiency.Wilson(diff, att_counts[a], 0.68, False)
    wilson_err_hi[a] = abs(wilson_bound_hi - att_counts[a]/diff)
    wilson_err_lo[a] = abs(att_counts[a]/diff - wilson_bound_lo)

    a_counts.append(att_counts[a])

#plot trigger efficiency vs attenuation

x_att = np.arange(0,32,0.5)
y_trig = []
y_trig_up = []
y_trig_lo = []
for att in x_att:
    y_trig.append(trig_eff[att])
    y_trig_up.append(wilson_err_hi[att])
    y_trig_lo.append(wilson_err_lo[att])

plt.figure()
plt.scatter(x_att, y_trig, color = "b")
plt.errorbar(x_att, y_trig, yerr = (y_trig_lo, y_trig_up), fmt="none", color = "b")
plt.xlabel("Attenuation")
plt.ylabel("Trigger Efficiency")
plt.title("Trigger Efficiency vs Attenuation")
plt.savefig("trig_vs_att_23_0.54.png")
plt.close()

#snr vs attenuation

indir = "/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/snr_npy_23_0.54"
#indir = "/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/snr_npy_11_0.65"
files = sorted(glob.glob(os.path.join(indir, "*")))

snr_means = []
snr_std = []
atts = []
atts_12 = []
snr_means_12 = []
snr_std_12 = []
for f in files:
    att_one = f.split("/")[-1].split("_")[-1].split(".")[0]
    att_two = f.split("/")[-1].split("_")[-1].split(".")[1]
    att = int(att_one) + 0.1*int(att_two)
    snr_arr = np.load(f)
    if (len(snr_arr) != 0):
        atts.append(att)
        snr_means.append(np.average(snr_arr))
        snr_std.append(np.std(snr_arr))
        if (att >= 6 and att <= 13):
            atts_12.append(att)
            snr_means_12.append(np.average(snr_arr))
            snr_std_12.append(np.std(snr_arr))


fit = scipy.optimize.curve_fit(lambda t,a,b: a*np.exp(b*t),  atts_12, snr_means_12,  p0=(17.5, -0.1), sigma = snr_std_12)
#fit = scipy.optimize.curve_fit(lambda t,a,b: a*np.exp(b*t),  atts_12, snr_means_12,  p0=(30, -0.2), sigma = snr_std_12)

fit_err = np.sqrt(np.diag(fit[1]))
a_err = fit_err[0]
b_err = fit_err[1]

x_vals = np.arange(0,32, 0.5)
y_vals = {}
SNR_err = {}


for x in x_vals:
    y_val = fit[0][0]*np.exp(fit[0][1]*x)
    y_vals[x] = y_val
    a = fit[0][0]
    b = fit[0][1]
    SNR_err[x] = y_val*np.sqrt((a_err**(2)/a**(2)) + x**(2)*b_err**(2)) #propagated snr error from fit


#logistic function
def f(x, b, c, d):
    return 1 / (1. + np.exp(-c * (x - d))) + b

#defining arrays of required length for snr and trigger efficiency
the_len = 0
atts = []
for key in trig_err.keys():
    if trig_err[key] != 0:
        the_len += 1
        atts.append(key)


#exporting dictionaries as csv files if needed
"""
with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/SNR_57.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for key, value in y_vals.items():
        writer.writerow([key, value])

with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/Trig_57.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for key, value in trig_eff.items():
        writer.writerow([key, value])

with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/SNR_err_57.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for key, value in SNR_err.items():
        writer.writerow([key, value])

with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/Wilson_lo_57.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for key, value in wilson_err_lo.items():
        writer.writerow([key, value])

with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/Wilson_hi_57.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for key, value in wilson_err_hi.items():
        writer.writerow([key, value])

"""

x_SNR = array('d', [0]*the_len)
y_trig = array('d', [0]*the_len)
y_err = array('d', [0]*the_len)
x_err = array('d', [0]*the_len)
y_err_hi = array('d', [0]*the_len)
y_err_lo = array('d', [0]*the_len)

i = 0
for att in np.arange(0,32,0.5):
    if (trig_err[att] != 0):
        x_SNR[i] = y_vals[att]
        y_trig[i] = trig_eff[att]
        y_err[i] = trig_err[att]
        x_err[i] = SNR_err[att]
        y_err_hi[i] = wilson_err_hi[att]
        y_err_lo[i] = wilson_err_lo[att]
        i += 1


#plot trigger efficiency vs snr and fit the logistic function
#prints out 50% efficiency point, chi^2 and p-value of the fit


c1 = ROOT.TCanvas( 'c1', 'Trigger Efficiency vs SNR', 200, 10, 700, 500 )

c1.SetGrid()
c1.GetFrame().SetFillColor( 21 )
c1.GetFrame().SetBorderSize( 12 )

n = 54;
x  = array( 'f', x_SNR )

exl = array( 'f', x_err )
exh = array( 'f', x_err )

eyl = array( 'f', y_err_lo )
eyh = array( 'f', y_err_hi )

ex = array( 'f', x_err )
y  = array( 'f', y_trig )
ey = array( 'f', y_err )

gr = ROOT.TGraphAsymmErrors( n, x, y, exl, exh, eyl, eyh )

log_fit = ROOT.TF1("LogisticFit", '1/(1+exp(-[1]*(x-[2]))) + [0]', 0, 20)
log_fit.SetParameter(0,-0.01)
log_fit.SetParameter(1,0.8)
log_fit.SetParameter(2,10.8)
gr.Fit("LogisticFit", "R")

fit_params = []
for i in range(3):
    fit_params.append(log_fit.GetParameter(i))

#save fit parameters if needed 

"""
with open('/data/condor_builds/users/avijai/RNO/tutorials-rnog/get_daqstatus/trig_snr_23_0.54/fit_params_54.csv', 'w') as csv_file:
    writer = csv.writer(csv_file)
    for i in range(len(fit_params)):
        writer.writerow((i, fit_params[i]))
"""

print(gr.Chisquare(log_fit), "chi2_eg")
print(log_fit.GetNDF(), log_fit.GetChisquare())
print(log_fit.GetChisquare()/log_fit.GetNDF())
print(log_fit.GetProb(), "p-val")

#plot trigger efficiency vs snr curve
dummy = ROOT.TH2D("","",2,0,32,2,0,1.2);
dummy.Draw("")
gr.Draw("sameP")
dummy.GetXaxis().SetTitle("SNR");
dummy.GetYaxis().SetTitle("Efficiency");
dummy.GetYaxis().SetRangeUser(0,1.2);
dummy.GetXaxis().SetRangeUser(0.,32.);

c1.Update()
c1.SaveAs("trig_vs_snr_23_0.54.png")

