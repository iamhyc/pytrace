#!/usr/bin/env python3
from re import L
import subprocess as sp
from datetime import datetime, time as TIME
from time import sleep

PROGRAM = './controller'

START_TIME = TIME(0, 00)
END_TIME   = TIME(8, 00)
assert(END_TIME > START_TIME)

global running_proc
running_proc = None

def start_running():
    global running_proc
    if running_proc:
        return
    running_proc = sp.Popen(PROGRAM, shell=True)
    pass

def stop_running():
    global running_proc
    if not running_proc:
        return
    running_proc.terminate()
    running_proc = None
    pass

while True:
    _now = datetime.now().time()
    if _now>=START_TIME and _now<=END_TIME:
        start_running()
    else:
        stop_running()
        print(f'Waiting for {START_TIME} ...')
    sleep(60)
    ##
    if running_proc and running_proc.poll() is not None:
        running_proc = None
        print('\nProgram abnormally exited.\n')
        sleep(30) #wait 30 seconds
    pass
