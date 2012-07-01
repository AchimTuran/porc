#!/usr/bin/env python 
#
# Python Open Room Correction (PORC)
# Copyright (c) 2012 Mason A. Green
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#   More details about the parallel filter can be found in the papers
#
#	Balazs Bank, "Perceptually Motivated Audio Equalization Using Fixed-Pole Parallel
#   Second-Order Filters", IEEE Signal Processing Letters, 2008.
#   http://www.acoustics.hut.fi/go/spl08-parfilt
#
#   Balazs Bank, "Direct Design of Parallel Second-order Filters for
#   Instrument Body Modeling", International Computer Music Conference,
#   Copenhagen, Denmark, Aug. 2007.
#   http://www.acoustics.hut.fi/go/icmc07-parfilt

# Python libs
import sys
import textwrap

# Scipy, Numpy, and matplotlibs
import numpy as np
from numpy.linalg import lstsq
import scipy as sp
import scipy.io as sio
from scipy.io import wavfile
import scipy.signal as sig
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import rc

# PORC source files
from parfiltid import parfiltid
from tfplot import tfplot, tfplots

# Ignore warnings
import warnings; warnings.filterwarnings('ignore')

# MiniDSP's OpenDRC box likes 6148 taps

def rceps(x): 
	y = sp.real(sp.ifft(sp.log(sp.absolute(sp.fft(x)))))
	n = len(x)
	w = np.hstack((1., 2.*np.ones(n/2-1), np.ones(1-n%2), np.zeros(n/2-1)))
	ym = sp.real(sp.ifft(sp.exp(sp.fft(w*y)))) 
	return (y, ym)

def parfilt(Bm, Am, FIR, x):
	y = np.zeros(x.size)
	for k in range(Am.shape[1]):
		y += np.ravel(sig.lfilter(Bm[:,k], Am[:,k], x))
	y += np.ravel(sig.lfilter(np.hstack([FIR]), np.hstack([1]), x))
	return y

def norm(y): return y/np.fabs(y, dtype = np.float64).max()

def roomcomp(impresp, filter, target, ntaps):
	
	###
	## Logarithmic pole positioning
	###

	Fs, data = wavfile.read(impresp)
	data = norm(np.hstack(data))

	# You may need to change this depending on the number of poles 
	# (more poles: larger, less poles: smaller)
	R = 0.5 
	# Two sets of log. resolution
	fplog = np.hstack((sp.logspace(sp.log10(30.), sp.log10(200.), 13.), sp.logspace(sp.log10(250.), 
					   sp.log10(18000.), 12.))) 

	wp = 2 * sp.pi * fplog / Fs
	p = np.power(R, wp/sp.pi) * np.exp(1j*wp)
	plog = np.hstack((p, np.conj(p)))

	###
	## Preparing data
	###

	# making the measured response minumum-phase
	cp, minresp = rceps(data)
	output = np.zeros(len(minresp), dtype=np.float64)
	# target
	output[0]=1.0
	
	outf = []
	
	if target is 'flat':
		# Make the target output a bandpass filter
		Bf, Af = sig.butter(4, 0, 'high')
		outf = sig.lfilter(Bf, Af, output)
	else:
		# load target file
		t = np.loadtxt(target)
		outf = sp.fft(sig.resample(sp.ifft(t[:,1]), len(minresp)))
	
	imp = np.zeros(len(data), dtype=np.float64)
	imp[0]=1.0

	###
	## Filter design
	###

	#Parallel filter design
	(Bm, Am, FIR) = parfiltid(minresp, outf, plog)

	# equalized loudspeaker response - filtering the 
	# measured transfer function by the parallel filter
	equalizedresp = norm(parfilt(Bm, Am, FIR, data))
										   
	# Equalizer impulse response - filtering a unit pulse
	equalizer = sp.fft(parfilt(Bm, Am, FIR, imp))
	
	# Resample in the frequency domain
	equalizer = sig.resample(equalizer, ntaps, window='hanning')
	equalizer = norm(np.real(sp.ifft(equalizer)))
	
	# Write data
	wavfile.write(filter, Fs, equalizer)
	 
	print '\nOutput filter length =', len(equalizer), 'taps'
	print 'Output filter written to ' + filter

	print "\nUse sox to convert output .wav to raw 32 bit IEEE floating point if necessary,"
	print "or to merge left and right channels into a stereo .wav"
	print "\nExample: sox leq48.wav -t f32 leq48.bin"
	print "         sox -M le148.wav req48.wav output.wav\n"

	###
	## Plots
	###
	
	# original loudspeaker-room response
	tfplot(data*70, Fs, avg = 'abs')
	# 1/3 Octave smoothed
	tfplots(data*70, Fs, 'r')
	
	# equalizer transfer function
	tfplot(equalizer, Fs)
	# indicating pole frequencies
	plt.vlines(fplog, -2, 2, color='k', linestyles='solid')
	
	# equalized loudspeaker-room response
	tfplot(equalizedresp*0.01, Fs, avg = 'abs')
	# 1/3 Octave smoothed
	tfplots(equalizedresp*0.01, Fs, 'r')
	
	tfplot(norm(outf), Fs, 'r')
	
	# Add labels
	# May need to reposition these based on input data
	plt.text(325,23,'Unequalized loudspeaker-room response')
	plt.text(100,-6,'Equalizer transfer function')
	plt.text(100,-10,'(Black lines: pole locations)')
	plt.text(200,-50,'Equalized loudspeaker-room response')

	a = plt.gca()
	a.set_xlim([20, 20000])
	a.set_ylim([-60, 65])
	plt.ylabel('Amplitude (dB)', color='b')
	plt.xlabel('Frequency (Hz)')
	plt.grid()
	plt.legend()
	plt.show()

def main():
	
	print
	
	mtxt = textwrap.dedent('''\
	Python Open Room Correction (PORC), version 0.1
	Copyright (c) 2012 Mason A. Green
	Based on the work of Dr. Balazs Bank
	''')
	
	bye = textwrap.dedent('''
	Example:
	./porc -t b&k.txt -n 8000 l48.wav leq48.bin
		
	See the README for detailed instructions
	''')
	
	import argparse
	from argparse import RawTextHelpFormatter
	
	parser = argparse.ArgumentParser(description = mtxt, epilog=bye, formatter_class=RawTextHelpFormatter)	

	# Positionals
	parser.add_argument('impresp', metavar='I', type=str, help='mesaured impulse response')
	parser.add_argument('filter', metavar='F', type=str, help='output filter file name')
	
	# Options
	parser.add_argument("-t", dest="target", default='flat',
					  help="target curve", metavar="FILE")
	parser.add_argument("-n", dest="ntaps", default = 65536,
					  help="filter length, in taps. Default = 65536", type=int)
		
	args = parser.parse_args()

	roomcomp(args.impresp, args.filter, args.target, args.ntaps)

if __name__=="__main__":
	main()	
	

