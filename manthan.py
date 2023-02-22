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

from __future__ import print_function
import sys
import os
import math
import random
import argparse
import copy
import tempfile
import numpy as np
from numpy import count_nonzero
from sklearn import tree
import collections
import subprocess as subprocess
import time
import networkx as nx
from src.DefinabilityChecker import DefinabilityChecker
from dependencies.rc2 import RC2Stratified
from pysat.formula import WCNF
import pydotplus

from collections import OrderedDict


from src.convert_verilog import convert_verilog
from src.preprocess import *
from src.callUnique import unique_function
from src.createSkolem import *
from src.generateSamples import *
from src.candidateSkolem import *
from src.repair import *


def logtime(inputfile, text):
    with open(inputfile+"time_details", "a+") as f:
        f.write(text + "\n")
    f.close()


def manthan():
    if args.verbose:
        print("Parsing")
    start_time = time.time()
    universally_quantified_vars, existentially_quantified_vars, qdimacs_list = parse(args.input)

    if args.verbose:
        print("Number of universally quantified variables (X):", len(universally_quantified_vars))
        print("Number of existentially quantified variables (Y)", len(existentially_quantified_vars))

    inputfile_name = args.input.split('/')[-1][:-8]
    cnffile_name = tempfile.gettempdir()+"/"+inputfile_name+".cnf"

    cnfcontent = convertcnf(args.input, cnffile_name)
    cnfcontent = cnfcontent.strip("\n")+"\n"

    if args.preprocess:
        print("preprocessing: finding unates (constant functions)")
        start_t = time.time()
        if len(existentially_quantified_vars) < 20000:
            PosUnate, NegUnate = preprocess(cnffile_name)
        else:
            print("Too many existentially quantified variables (Y), let us proceed with Unique extraction\n")
            PosUnate = []
            NegUnate = []
        end_t = time.time()
        logtime(inputfile_name, "preprocessing time:"+str(end_t-start_t))

        if args.verbose:
            print("count of positive unates", len(PosUnate))
            print("count of negative unates", len(NegUnate))
            if args.verbose >= 2:
                print("positive unates", PosUnate)
                print("negative unates", NegUnate)

        Unates = PosUnate + NegUnate

        for eq_var in PosUnate:
            qdimacs_list.append([eq_var])
            cnfcontent += "%s 0\n" % (eq_var)

        for eq_var in NegUnate:
            qdimacs_list.append([-1 * int(eq_var)])
            cnfcontent += "-%s 0\n" % (eq_var)

    else:
        Unates = []
        PosUnate = []
        NegUnate = []
        print("preprocessing is disabled. To do preprocessing, please use --preprocess")

    if len(Unates) == len(existentially_quantified_vars):
        print(PosUnate)
        print(NegUnate)
        print("All existentially quantified variables (Y) are unates and have constant functions")
        skolemfunction_preprocess(
            universally_quantified_vars, existentially_quantified_vars, PosUnate, NegUnate, [], '', inputfile_name)
        end_time = time.time()
        logtime(inputfile_name, "totaltime:"+str(end_time-start_time))
        exit()

    dg = nx.DiGraph()  # dag to handle dependencies

    if args.unique:
        print("finding uniquely defined functions")
        start_t = time.time()
        UniqueVars, UniqueDef = unique_function(
            qdimacs_list, universally_quantified_vars, existentially_quantified_vars, dg, Unates)
        end_t = time.time()
        logtime(inputfile_name, "unique function finding:"+str(end_t-start_t))

        if args.verbose:
            print("count of uniquely defined variables", len(UniqueVars))
            if args.verbose >= 2:
                print("uniquely defined variables", UniqueVars)
    else:
        UniqueVars = []
        UniqueDef = ''
        print("finding unique function is disabled. To find unique functions please use -- unique")

    if len(Unates) + len(UniqueVars) == len(existentially_quantified_vars):
        print("All existentially quantified variables (Y) are either unate or unique.")
        print("Found functions for all existentially quantified variables (Y).")
        if args.preprocess:
            skolemfunction_preprocess(
                universally_quantified_vars, existentially_quantified_vars, PosUnate, NegUnate, UniqueVars, UniqueDef, inputfile_name)
        else:
            skolemfunction_preprocess(
                universally_quantified_vars, existentially_quantified_vars, [], [], UniqueVars, UniqueDef, inputfile_name)
        end_time = time.time()
        logtime(inputfile_name, "totaltime:"+str(end_time-start_time))
        exit()

    # we need verilog file for repairing the candidates, hence first let us convert the qdimacs to verilog
    print("parsing and converting to verilog")
    verilogformula, dg, ng = convert_verilog(args.input, args.multiclass, dg)

    start_t = time.time()

    sampling_cnf = cnfcontent
    if not args.maxsamples:
        if len(universally_quantified_vars) > 4000:
            num_samples = 1000
        if (len(universally_quantified_vars) > 1200) and (len(universally_quantified_vars) <= 4000):
            num_samples = 5000
        if len(universally_quantified_vars) <= 1200:
            num_samples = 10000
    else:
        num_samples = args.maxsamples

    if args.weighted:
        sampling_weights_y_1 = ''
        sampling_weights_y_0 = ''
        for uq_var in universally_quantified_vars:
            sampling_cnf += "w %s 0.5\n" % (uq_var)
        for eq_var in existentially_quantified_vars:
            if eq_var in UniqueVars:
                sampling_cnf += "w %s 0.5\n" % (eq_var)
                continue
            if (eq_var in PosUnate) or (eq_var in NegUnate):
                continue

            sampling_weights_y_1 += "w %s 0.9\n" % (eq_var)
            sampling_weights_y_0 += "w %s 0.1\n" % (eq_var)

        if args.adaptivesample:
            weighted_sampling_cnf = computeBias(
                universally_quantified_vars, existentially_quantified_vars, sampling_cnf, sampling_weights_y_1, sampling_weights_y_0, inputfile_name, Unates + UniqueVars, args)
        else:
            weighted_sampling_cnf = sampling_cnf + sampling_weights_y_1

        print("generating weighted samples")
        samples = generatesample(
            args, num_samples, weighted_sampling_cnf, inputfile_name, 1)
    else:
        print("generating uniform samples")
        samples = generatesample(
            args, num_samples, sampling_cnf, inputfile_name, 0)

    end_t = time.time()
    logtime(inputfile_name, "generating samples:"+str(end_t-start_t))

    print("generated samples.. learning candidate functions")
    start_t = time.time()

    candidateSkf, dg = learnCandidate(
        universally_quantified_vars, existentially_quantified_vars, UniqueVars, PosUnate, NegUnate, samples, dg, ng, args)

    end_t = time.time()
    logtime(inputfile_name, "candidate learning:"+str(end_t-start_t))

    YvarOrder = np.array(list(nx.topological_sort(dg)))

    assert(len(existentially_quantified_vars) == len(YvarOrder))

    createSkolem(candidateSkf, universally_quantified_vars, existentially_quantified_vars, UniqueVars,
                 UniqueDef, inputfile_name)

    error_content = createErrorFormula(universally_quantified_vars, existentially_quantified_vars, UniqueVars, verilogformula)

    maxsatWt, maxsatcnf, cnfcontent = maxsatContent(
        cnfcontent, (len(universally_quantified_vars)+len(existentially_quantified_vars)), (len(PosUnate)+len(NegUnate)))

    countRefine = 0

    start_t = time.time()

    while True:
        addSkolem(error_content, inputfile_name)
        check, sigma, ret = verify(universally_quantified_vars, existentially_quantified_vars, inputfile_name)
        if check == 0:
            print("error --- ABC network read fail")
            break
        if ret == 0:
            print("verification check UNSAT")
            print("no more repair needed")
            print("number of repairs needed to converge", countRefine)
            createSkolemfunction(inputfile_name, universally_quantified_vars, existentially_quantified_vars)
            break
        if ret == 1:
            countRefine += 1
            print("verification check is SAT, we have counterexample to fix")
            if args.verbose:
                print("number of repair", countRefine)
                print("finding candidates to repair using maxsat")

            repaircnf, maxsatcnfRepair = addXvaluation(
                cnfcontent, maxsatWt, maxsatcnf, sigma[0], universally_quantified_vars)

            ind = callMaxsat(
                maxsatcnfRepair, sigma[2], UniqueVars, Unates, existentially_quantified_vars, YvarOrder, inputfile_name, args.weightedmaxsat)

            assert(len(ind) > 0)

            if args.verbose == 1:
                print("number of candidates undergoing repair iterations", len(ind))
            if args.verbose == 2:
                print("number of candidates undergoing repair iterations", len(ind))
                print("variables undergoing refinement", ind)

            lexflag, repairfunctions = repair(
                repaircnf, ind, universally_quantified_vars, existentially_quantified_vars, YvarOrder, UniqueVars, Unates, sigma, inputfile_name, args, args.lexmaxsat)

            if lexflag:
                print("calling rc2 to find another set of candidates to repair")
                ind = callRC2(maxsatcnfRepair,
                              sigma[2], UniqueVars, Unates, existentially_quantified_vars, YvarOrder)
                assert(len(ind) > 0)
                if args.verbose == 1:
                    print("number of candidates undergoing repair iterations", len(ind))
                lexflag, repairfunctions = repair(
                    repaircnf, ind, universally_quantified_vars, existentially_quantified_vars, YvarOrder, UniqueVars, Unates, sigma, inputfile_name, args, 0)
            updateSkolem(repairfunctions, countRefine,
                         sigma[2], inputfile_name, existentially_quantified_vars)
        if countRefine > args.maxrepairitr:
            print("number of maximum allowed repair iteration reached")
            print("could not synthesize functions")
            break
    end_time = time.time()
    logtime(inputfile_name, "repair time:"+str(end_time-start_t))
    logtime(inputfile_name, "totaltime:"+str(end_time-start_time))


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('--seed', type=int, default=10, dest='seed')
    parser.add_argument('--verb', type=int, help="0 ,1 ,2", default=1, dest='verbose')
    parser.add_argument(
        '--gini', type=float, help="minimum impurity drop, default = 0.005", default=0.005, dest='gini')
    parser.add_argument('--weightedsampling', type=int, default=1,
                        help="weighted sampling: 1; uniform sampling: 0; default 1", dest='weighted')
    parser.add_argument('--maxrepairitr', type=int, default=5000,
                        help="maximum allowed repair iterations; default 1000", dest='maxrepairitr')
    parser.add_argument('--selfsubthres', type=int, default=30,
                        help="self substitution threshold", dest='selfsubthres')
    parser.add_argument('--adaptivesample', type=int, default=1,
                        help="required --weighted to 1: to enable/disable adaptive weighted sampling ", dest='adaptivesample')
    parser.add_argument('--showtrees', type=int, default=0,
                        help="To see the decision trees: 1; default 0", dest='showtrees')
    parser.add_argument('--maxsamples', type=int,
                        help="samples used to learn", dest='maxsamples')
    parser.add_argument("--preprocess", type=int, help="0 ,1 ", default=1, dest='preprocess')
    parser.add_argument("--multiclass", action='store_true')
    parser.add_argument("--weightedmaxsat", action='store_true')
    parser.add_argument("--lexmaxsat", action='store_true')
    parser.add_argument("--hop", type=int, default=3, dest='hop')
    parser.add_argument("--clustersize", type=int,
                        default=8, dest='clustersize')
    parser.add_argument("--unique", type=int, help="0 ,1 ", default=1, dest='unique')
    parser.add_argument("input", help="input file")
    args = parser.parse_args()
    print("starting Manthan")
    manthan()
