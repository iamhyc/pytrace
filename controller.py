#!/usr/bin/env python3
import os, sys
import pytrace
from halo import Halo
from paramiko import SSHClient
import subprocess as sp

SHELL_RUN = lambda x: sp.run(x, stdout=sp.PIPE, stderr=sp.PIPE, check=True, shell=True)
TOS_SET = [0, 32, 128, 192]
BW_SET  = list(range(0, 105, 5))

##
PARAM_ENCODE = lambda bw,tos: (bw<<8)|(tos)
PARAM_DECODE = lambda _code: (_code>>8, _code&0xFF)
BEGIN_PARAM  = ( min(BW_SET), min(TOS_SET) )
END_PARAM    = ( max(BW_SET), max(TOS_SET) )
IS_ENDED     = lambda param: param==END_PARAM
##
def NEXT_PARAM(param):
    _bw, _tos = param
    if _bw != BW_SET[-1]:
        _bw = BW_SET[ BW_SET.index(_bw)+1]
    elif _tos != TOS_SET[-1]:
        _bw = 0
        _tos = TOS_SET[ TOS_SET.index(_tos)+1 ]
    return (_bw, _tos)
##
def NEXT_EVA_PARAMS(eva_params):
    for _idx,_param in enumerate(eva_params):
        if IS_ENDED( _param ):
            eva_params[_idx] = BEGIN_PARAM
            continue
        else:
            eva_params[_idx] = NEXT_PARAM(_param)
            return eva_params
    return None
##

RECORDER_ADDR = '127.0.0.1'
RECORDER_USER = 'lab525'
EVA_CLIENTS  = {
    # '10.42.0.1': {'username': 'lab525'},
    # '10.42.0.2': {'username': 'lab525'},
    # '10.42.0.3': {'username': 'lab525'},
}
_EVA_CLIENTS = {
    '10.42.0.1': {'username': 'lab525'},
    '10.42.0.2': {'username': 'lab525'},
}

## Initialize ssh-key copy
# assert( os.system('which sshpass')==0 )
_cmd = 'ssh-copy-id -o StrictHostKeyChecking=accept-new {username}@{addr}'
SHELL_RUN( _cmd.format(addr=RECORDER_ADDR, username=RECORDER_USER) )
for addr, info in EVA_CLIENTS.items():
    SHELL_RUN( _cmd.format(addr=addr, username=info['username']) )

## Setup recorder's connection
recorder_conn = SSHClient()
recorder_conn.load_system_host_keys()
recorder_conn.connect(RECORDER_ADDR, username=RECORDER_USER)

## Setup interference clients' connections
eva_conns = [ ]
for addr, info in EVA_CLIENTS.items():
    conn = SSHClient()
    conn.load_system_host_keys()
    conn.look_for_keys(True)
    conn.connect(addr, username=info['username'])
    eva_conns.append( conn )

## Initialize parameters setup
if len(sys.argv) == 2:
    r_param, *e_params = sys.argv[1].split(',')
    recorder_param = PARAM_DECODE(r_param)
    eva_params = [ PARAM_DECODE(_param) for _param in e_params ]
else:
    recorder_param = BEGIN_PARAM
    eva_params = [ BEGIN_PARAM for _ in _EVA_CLIENTS ]

## Execute Remote Control
_all = set()
while eva_params is not None:
    #TODO: filter redundant iteration
    ## update parameters
    recorder_param = NEXT_PARAM(recorder_param)
    eva_params = NEXT_EVA_PARAMS(eva_params)
    pass
