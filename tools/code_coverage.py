#!/usr/bin/env python2
# -*- coding: utf-8 -*-
##
##  Triton tool to perform code coverage
##  Romain Thomas - 2015-09-26
##
## Description:
## ------------
##
## This tool aims to reach all basic blocks in a program using dynamic symbolic
## resolution and the snapshot engine. The algorithm is based on Microsoft SAGE's
## fuzzer.
##
##
## Output:
## -------
##
## $ ./triton ./tools/code_coverage.py ./samples/code_coverage/test_atoi a
## [+] Take Snapshot
## [+] In main
## [+] In main() we set :
##         [0x7ffc92bdc54a] = 61 a
##         [0x7ffc92bdc54b] = 61 a
##         [0x7ffc92bdc54c] = 61 a
## [+] Exit point
## {140722770396490: 0}
## {140722770396490: 32}
## {140722770396490: 57}
## [+] Restore snapshot
## [+] In main
## [+] In main() we set :
##         [0x7ffc92bdc54a] = 39 9
##         [0x7ffc92bdc54b] = 61 a
##         [0x7ffc92bdc54c] = 61 a
## [+] Exit point
## {140722770396490: 57, 140722770396491: 0}
## {140722770396490: 57, 140722770396491: 8}
## {140722770396490: 56, 140722770396491: 56}
## [+] Restore snapshot
## [+] In main
## [+] In main() we set :
##         [0x7ffc92bdc54a] = 38 8
##         [0x7ffc92bdc54b] = 38 8
##         [0x7ffc92bdc54c] = 61 a
## [+] Exit point
## {140722770396490: 56, 140722770396491: 56, 140722770396492: 0}
## {140722770396490: 57, 140722770396491: 57, 140722770396492: 8}
## {140722770396490: 57, 140722770396491: 57, 140722770396492: 56}
## {140722770396490: 51, 140722770396491: 51, 140722770396492: 63}
## [+] Restore snapshot
## [+] In main
## [+] In main() we set :
##         [0x7ffc92bdc54a] = 33 3
##         [0x7ffc92bdc54b] = 33 3
##         [0x7ffc92bdc54c] = 3f ?
## ok
## [+] Exit point
## [+] Done !
## $
##

import  smt2lib
from    triton      import *
from    collections import OrderedDict



class Input(object):

    def __init__(self, data):
        self.__data = data
        self.__bound = 0
        self.__dataAddr = dict()

    @property
    def data(self):
        return self.__data

    @property
    def bound(self):
        return self.__bound

    @property
    def dataAddr(self):
        return self.__dataAddr

    def setBound(self, bound):
        self.__bound = bound

    def addDataAddress(self, address, value):
        self.__dataAddr[address] = value



class TritonExecution(object):

    program     = None
    input       = None
    worklist    = None
    inputTested = None
    entryPoint  = 0
    exitPoint   = 0
    whitelist   = None
    myPC        = None

    @staticmethod
    def cbefore(instruction):

        if instruction.getAddress() == TritonExecution.entryPoint + 2:
            TritonExecution.myPC = []                                  # Reset the path constraint
            TritonExecution.input = TritonExecution.worklist.pop()     # Take the first input
            TritonExecution.inputTested.append(TritonExecution.input)  # Add this input to the tested input
            return

        if instruction.getAddress() == TritonExecution.entryPoint and not isSnapshotEnabled():
            print "[+] Take Snapshot"
            takeSnapshot()
            return

        if instruction.isBranch() and instruction.getRoutineName() in TritonExecution.whitelist:

            addr1 = instruction.getNextAddress()                         # next address next from the current one
            addr2 = instruction.getOperands()[0].getImm().getValue()     # Address in the instruction condition (branch taken)

            ripId = getRegSymbolicID(IDREF.REG.RIP)                      # Get the reference of the RIP symbolic register

            # [PC id, address taken, address not taken]
            if instruction.isBranchTaken():
                TritonExecution.myPC.append([ripId, addr2, addr1])
            else:
                TritonExecution.myPC.append([ripId, addr1, addr2])

            return

        if instruction.getAddress() == TritonExecution.exitPoint:
            print "[+] Exit point"

            # SAGE algorithm
            # http://research.microsoft.com/en-us/um/people/pg/public_psfiles/ndss2008.pdf
            for j in range(TritonExecution.input.bound, len(TritonExecution.myPC)):
                expr = []
                for i in range(0,j):
                    ripId = TritonExecution.myPC[i][0]
                    symExp = getFullExpression(getSymExpr(ripId).getAst())
                    addr = TritonExecution.myPC[i][1]
                    expr.append(smt2lib.smtAssert(smt2lib.equal(symExp, smt2lib.bv(addr,  64))))

                ripId = TritonExecution.myPC[j][0]
                symExp = getFullExpression(getSymExpr(ripId).getAst())
                addr = TritonExecution.myPC[j][2]
                expr.append(smt2lib.smtAssert(smt2lib.equal(symExp, smt2lib.bv(addr,  64))))

                expr = smt2lib.compound(expr)
                model = getModel(expr)

                if len(model) > 0:
                    newInput = TritonExecution.input
                    newInput.setBound(j + 1)

                    for k,v in model.items():
                        symVar = getSymVar(k)
                        newInput.addDataAddress(symVar.getKindValue(), v)
                    print newInput.dataAddr

                    isPresent = False

                    for inp in TritonExecution.worklist:
                        if inp.dataAddr == newInput.dataAddr:
                            isPresent = True
                            break
                    if not isPresent:
                        TritonExecution.worklist.append(newInput)

            # If there is input to test in the worklist, we restore the snapshot
            if len(TritonExecution.worklist) > 0 and isSnapshotEnabled():
                print "[+] Restore snapshot"
                restoreSnapshot()
            return
        return


    @staticmethod
    def fini():
        print '[+] Done !'
        return


    @staticmethod
    def mainAnalysis(threadId):

        print "[+] In main"
        rdi = getRegValue(IDREF.REG.RDI) # argc
        rsi = getRegValue(IDREF.REG.RSI) # argv

        argv0_addr = getMemValue(rsi, IDREF.CPUSIZE.QWORD)      # argv[0] pointer
        argv1_addr = getMemValue(rsi + 8, IDREF.CPUSIZE.QWORD)  # argv[1] pointer

        print "[+] In main() we set :"
        od = OrderedDict(sorted(TritonExecution.input.dataAddr.items()))

        for k,v in od.iteritems():
            print "\t[0x%x] = %x %c" % (k, v, v)
            setMemValue(k, IDREF.CPUSIZE.BYTE, v)
            convertMemToSymVar(k, IDREF.CPUSIZE.BYTE, "addr_%d" % k)

        for idx, byte in enumerate(TritonExecution.input.data):
            if argv1_addr + idx not in TritonExecution.input.dataAddr: # Not overwrite the previous setting
                print "\t[0x%x] = %x %c" % (argv1_addr + idx, ord(byte), ord(byte))
                setMemValue(argv1_addr + idx, IDREF.CPUSIZE.BYTE, ord(byte))
                convertMemToSymVar(argv1_addr + idx, IDREF.CPUSIZE.BYTE, "addr_%d" % idx)


    @staticmethod
    def run(inputSeed, entryPoint, exitPoint, whitelist = []):

        TritonExecution.exitPoint   = exitPoint
        TritonExecution.entryPoint  = entryPoint
        TritonExecution.worklist    = [Input(inputSeed)]
        TritonExecution.inputTested = []
        TritonExecution.whitelist   = whitelist

        startAnalysisFromAddr(entryPoint)

        addCallback(TritonExecution.mainAnalysis,   IDREF.CALLBACK.ROUTINE_ENTRY, "main") # Called when we are in main's beginning
        addCallback(TritonExecution.cbefore,        IDREF.CALLBACK.BEFORE)
        addCallback(TritonExecution.fini,           IDREF.CALLBACK.FINI)
        runProgram()



if __name__=='__main__':
    TritonExecution.run("aaa", 0x4004a0, 0x40065D, ["main", "myatoi"])  # ./triton ./tools/code_coverage.py ./samples/code_coverage/test_atoi a
    #TritonExecution.run("bad !", 0x400480, 0x40061B, ["main", "check"]) # ./triton ./tools/code_coverage.py ./samples/crackmes/crackme_xor abc

