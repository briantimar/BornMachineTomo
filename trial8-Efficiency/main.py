# -*- coding: utf-8 -*-
from mpi4py import MPI
import sys
sys.path.append('../')
from CS6 import ProjMeasureSet, MPS, MLETomoTrainer # From trial8
import numpy as np
import os
from time import time

import matplotlib as mpl 
mpl.use('Agg')
import matplotlib.pyplot as plt

measout_dir = "../MeasOutcomes/"

def plot_rdsd(V, **kwarg):
	rfs = kwarg['real']
	sfs = kwarg['succ']
	N = rfs.shape[0]
	fig, axs = plt.subplots(2,1,sharex=True)
	xi = np.log10(V)
	lns = []
	for r in range(N):
		l = axs[0].plot(xi,((1-rfs[r]**2)*0.5)**0.5, label=r)
		lns.append(l[0])
		axs[1].plot(xi,((1-sfs[r]**2)*0.5)**0.5, label=r)
	axs[0].set_yscale('log')
	axs[0].set_ylabel('real distance')
	axs[1].set_yscale('log')
	axs[1].set_ylabel('successive distance')
	axs[1].set_xlabel('lg|V|')
	axs[0].plot([np.log10(80),np.ceil(np.log10(V.max())*2)/2.],[np.sqrt((1-0.995**2)/2)]*2,':',color='gray')
	plt.xlim(np.log10(80),np.ceil(np.log10(V.max())*2)/2.)
	# fig.legend(lns, range(N), loc=10, bbox_to_anchor=(.9,0.5), ncol=min(3,N//10))
	
def saturation_statis(realfids, V, thres):
	saturateV = np.zeros((realfids.shape[0],),np.uint32)
	for r in range(realfids.shape[0]):
		saturation_point = np.argwhere(realfids[r] < thres).max()+1
		if saturation_point < realfids.shape[1]:
			saturateV[r] = V[saturation_point]
	return saturateV

def saturation_analyz(saturateV):
	msaturateV = np.ma.masked_array(saturateV, saturateV==0)
	nfail = sum(saturateV==0)
	if (saturateV==0).all():
		return -1, -1, nfail
	else:
		return msaturateV.mean(), msaturateV.std(), nfail

def metaTrain(m, brange, nloop, **kwarg):
	for kw in kwarg:
		setattr(m, kw, kwarg[kw])
	for b in range(brange[0],brange[1]):
		m.train(nloop)
		if b%10==9 or b == brange[1]-1:
			m.save('L%d'%b)

def findLatest(srch_pwd):
	nams = os.listdir(srch_pwd)
	ibatches = []
	for nm in nams:
		if nm[0]=='L':
			ibatches.append(int(nm[1:]))
	return max(ibatches)

if __name__ == '__main__':
	work_mode = sys.argv[1] # 'start' or 'continue'
	typ = sys.argv[2]
	space_size = int(sys.argv[3])

	comm = MPI.COMM_WORLD
	rk = comm.Get_rank()
	# rk=0 # Debugging
	# rk=0
	if rk==0:
		t0 = time()

	ds = ProjMeasureSet(space_size)
	ds.load("%s/%s/%d/R%dSet"%(measout_dir, typ, space_size, rk))

	wd = './%s/%d/R%d/'%(typ,space_size,rk)
	if work_mode=='start':
		np.random.seed(rk)

		try:
			os.makedirs(wd)
		except FileExistsError:
			pass
		os.chdir(wd)

		m = MLETomoTrainer(ds, batch_size=40, initV=80, add_mode=True)
		m.grad_mode = 'plain'
		if space_size >= 40:
			mxBatch = 500
		elif space_size >= 30:
			mxBatch = 450
		else:
			mxBatch = 300

		nloop = 1
		m.descent_steps = 1
		m.learning_rate = 0.1
		m.penalty_rate = None

		# m.cutoff = 0.8
		# m.train(nloop)
		b = 0
		# for qq in range(5):
		# 	metaTrain(m, (b,b+3), nloop, cutoff=0.01, Dmax=20)
		# 	b += 3
		# 	metaTrain(m, (b,b+3), nloop, cutoff=0.01, Dmax=10)
		# 	b += 3
		if space_size >= 20:
			for qq in range(5):
				metaTrain(m, (b,b+3), nloop, cutoff=0.005, Dmax=10)
				b += 3
				metaTrain(m, (b,b+3), nloop, cutoff=0.005, Dmax=5)
				b += 3
		if space_size >= 10:
			for qq in range(5):
				metaTrain(m, (b,b+3), nloop, cutoff=0.002, Dmax=3)
				b += 3
				metaTrain(m, (b,b+3), nloop, cutoff=0.002, Dmax=5)
				b += 3
		for qq in range(5):
			metaTrain(m, (b,b+3), nloop, cutoff=0.005, Dmax=2)
			b += 3
			metaTrain(m, (b,b+3), nloop, cutoff=0.005, Dmax=3)
			b += 3
		metaTrain(m, (b,mxBatch), nloop, cutoff=0.8, Dmax=2)
		
		if rk==0:
			with open('../duration.log','w') as fd:
				print(time()-t0,file=fd)
	elif work_mode =='continue':
		os.chdir(wd)
		lmax = findLatest('./')
		m = MLETomoTrainer(ds, batch_size=40, initV=80, add_mode=True)
		m.load('L%d'%lmax)

		extension_nbatch = int(sys.argv[4])
		mxBatch = lmax+1+extension_nbatch
		if m.dat_rear + extension_nbatch * m.batch_size > len(ds.spinor_outcomes):
			print("Re-measuring rk=%d, up to %d"%(rk,m.dat_rear + 2*extension_nbatch * m.batch_size))
			ds.spinor_outcomes = []
			np.random.seed(rk)
			ds.measureUpTo(m.dat_rear + 2*extension_nbatch * m.batch_size)
			ds.save("%s/%s/%d/R%dSet"%(measout_dir, typ, space_size, rk))
		
		b = lmax+1
		nloop = 1
		metaTrain(m, (b,mxBatch), nloop, cutoff=0.8, Dmax=2)

		if rk==0:
			duration = time()-t0
			with open('../duration.log','a') as fd:
				print("L%d-L%d: %g"%(lmax+1, mxBatch-1, time()-t0),file=fd)

	if rk==0:
		realfids = np.empty((comm.Get_size(), len(m.real_fid)),dtype='d')
		succfids = np.empty((comm.Get_size(), len(m.succ_fid)),dtype='d')
	else:
		realfids = None
		succfids = None
	comm.Gather(np.asarray(m.real_fid), realfids, root=0)
	comm.Gather(np.asarray(m.succ_fid), succfids, root=0)
	if rk==0:
		Vs = np.asarray([t[-2]-t[-3] for t in m.train_history])
		# print(Vs)
		np.savez("../fids.npz",succ=succfids,real=realfids,V=Vs)
		plot_rdsd(Vs, real=realfids, succ=succfids)
		plt.savefig('../rdsd_V.pdf')

		saturateV = saturation_statis(realfids, Vs, 0.995)
		mean_val, std_val, nfail = saturation_analyz(saturateV)
		print("mean=%.2f, std=%.2f, nfail=%d"%(mean_val, std_val, nfail))
		np.savez("../saturation.npz", saturateV=saturateV,mean=mean_val, std=std_val, nfail=nfail)
