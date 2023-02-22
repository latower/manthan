#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Copyright (C) 2021 Priyanka Golia, Subhajit Roy, and Kuldeep Meel

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
'''




import tempfile
from subprocess import Popen, PIPE, check_output
import signal
import os
import numpy as np

def parse(inputfile):
	with open(inputfile) as f:
		lines = f.readlines()
	f.close()

	universally_quantified_vars = []
	existentially_quantified_vars = []

	qdimacs_list = []
	for line in lines:
		if line.startswith("c"):
			continue
		if (line == "") or (line == "\n"):
			continue
		if line.startswith("p"):
			continue
		if line.startswith("a"):
			universally_quantified_vars += line.strip("a").strip("\n").strip(" ").split(" ")[:-1]
			continue
		if line.startswith("e"):
			existentially_quantified_vars += line.strip("e").strip("\n").strip(" ").split(" ")[:-1]
			continue
		clause = line.strip(" ").strip("\n").strip(" ").split(" ")[:-1]

		if len(clause) > 0:
			clause = list(map(int, list(clause)))
			qdimacs_list.append(clause)

	assert len(universally_quantified_vars) > 0, "Please specify the universally quantified variables X."
	assert len(existentially_quantified_vars) > 0, "Please specify the existentially quantified variables Y."
	assert len(qdimacs_list) > 0, "Please specify clauses."
	
	universally_quantified_vars = list(map(int, list(universally_quantified_vars)))
	existentially_quantified_vars = list(map(int, list(existentially_quantified_vars)))

	return universally_quantified_vars, existentially_quantified_vars, qdimacs_list


def convertcnf(inputfile, cnffile_name):
	with open(inputfile,"r") as f:
		cnfcontent = f.read()
	f.close()

	cnfcontent = cnfcontent.replace("a ", "c ret ")
	cnfcontent = cnfcontent.replace("e ", "c ind ")

	with open(cnffile_name,"w") as f:
		f.write(cnfcontent)
	f.close()
	return cnfcontent


def preprocess(cnffile_name):

	cmd = "./dependencies/preprocess %s " % (cnffile_name)
	with Popen(cmd, shell=True, stdout=PIPE, preexec_fn=os.setsid) as process:
		try:
			output = process.communicate(timeout=500)[0]
		except Exception:
			os.killpg(process.pid, signal.SIGINT)
			PosUnate = []
			NegUnate = []
			print("timeout preprocessing..")
			return PosUnate, NegUnate
		else:
			PosUnate = []
			NegUnate = []
			exists = os.path.isfile(cnffile_name + "_vardetails")
			if exists:
				with open(cnffile_name + "_vardetails", 'r') as f:
					lines = f.readlines()
				f.close()

				for line in lines:
					if "Posunate" in line:
						pos = line.split(":")[1].strip(" \n")
						if pos != "":
							PosUnate = list(map(int, list(pos.split(" "))))
						continue
					if "Negunate" in line:
						neg = line.split(":")[1].strip(" \n")
						if neg != "":
							NegUnate = list(map(int, list(neg.split(" "))))
						continue
				os.unlink(cnffile_name + "_vardetails")
			else:
				print("preprocessing error .. contining ")
				exit()
			return PosUnate, NegUnate




