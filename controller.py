#!/usr/bin/env python3
import os, sys, time
from itertools import permutations
from halo import Halo
from paramiko import SSHClient
import subprocess as sp

REPEATED_TIMES    = 5
REPEATED_DURATION = 20

IPERF3_SERVER = '192.168.2.1'
EVA_PORTS  = [5202, 5203, 5204]

RECORDER_ADDR = '127.0.0.1'
RECORDER_USER = 'lab525pr'
# RECORDER_PWD  = 'lablab'
EVA_CLIENTS  = {
    '192.168.43.102': {'username': 'lab525'},
    '192.168.43.103': {'username': 'lab525'},
    '192.168.43.100': {'username': 'snowflame'},
}

##
SHELL_RUN = lambda x: sp.run(x, stdout=sp.PIPE, stderr=sp.PIPE, check=True, shell=True)
TOS_SET = [0, 32, 128, 192]
BW_SET  = [0, 200] #list(range(0, 105, 5))

PARAM_ENCODE = lambda bw,tos: (bw<<8)|(tos)
PARAM_DECODE = lambda _code: (_code>>8, _code&0xFF)
BEGIN_PARAM  = ( min(BW_SET), min(TOS_SET) )
END_PARAM    = ( max(BW_SET), max(TOS_SET) )
IS_ENDED     = lambda param: param==END_PARAM

def NEXT_PARAM(param):
    _bw, _tos = param
    if _bw != BW_SET[-1]:
        _bw = BW_SET[ BW_SET.index(_bw)+1 ]
    elif _tos != TOS_SET[-1]:
        _bw = BW_SET[1]
        _tos = TOS_SET[ TOS_SET.index(_tos)+1 ]
    return (_bw, _tos)

def NEXT_ALL_PARAMS(r_param, e_params):
    all_params = [r_param] + e_params
    for _idx,_param in enumerate(all_params):
        if IS_ENDED( _param ):
            all_params[_idx] = BEGIN_PARAM
            continue
        else:
            all_params[_idx] = NEXT_PARAM(_param)
            return all_params[0], all_params[1:]
    return (r_param, None)
##
def Execute(conn, cmd):
    _, stdout, stderr = conn.exec_command(cmd, get_pty=True)
    output = stdout.read()
    error = stderr.read()
    # print(output, error)
    if error:
        raise Exception(error)
    else:
        return output.decode().strip()
def Send_SIGINT(_idx, stdin):
    try:
        stdin.write( chr(3) )
        stdin.flush()
    except Exception as e:
        print('??????')
        print(_idx)
        raise e
    pass

def IS_REDUNDANT(conn, params) -> bool:
    r_param, e_params = params[0], params[1:]
    all_combinations = permutations(e_params)
    for _params in all_combinations:
        _prefix = '-'.join([r_param]+list(_params))
        _file   = f'pytrace-logs/{_prefix}.flag'
        _output = Execute(conn, f'ls {_file}').strip()
        if _file==_output:
            return True
    return False


## Initialize ssh-key copy
# assert( os.system('which sshpass')==0 )
_cmd = 'ssh-copy-id -o StrictHostKeyChecking=accept-new {username}@{addr}'
SHELL_RUN( _cmd.format(addr=RECORDER_ADDR, username=RECORDER_USER) )
for addr, info in EVA_CLIENTS.items():
    SHELL_RUN( _cmd.format(addr=addr, username=info['username']) )

## Setup recorder's connection
recorder_conn = SSHClient()
recorder_conn.load_system_host_keys()
recorder_conn.connect(RECORDER_ADDR, username=RECORDER_USER, timeout=1000000)
Execute(recorder_conn, f'mkdir -p pytrace-logs')

## Setup interference clients' connections
eva_conns = [ ]
for addr, info in EVA_CLIENTS.items():
    conn = SSHClient()
    conn.load_system_host_keys()
    conn.connect(addr, username=info['username'], timeout=1000000)
    eva_conns.append( conn )

## Initialize parameters setup
if len(sys.argv) == 2:
    r_param, *e_params = sys.argv[1].split('-', maxsplit=1)
    recorder_param = PARAM_DECODE(r_param)
    eva_params = [ PARAM_DECODE(_param) for _param in e_params ]
else:
    recorder_param = (2, 0) #BEGIN_PARAM
    eva_params = [ BEGIN_PARAM for _ in EVA_CLIENTS ]

## Execute Remote Control
counter = 0
while eva_params is not None:
    with Halo('Ready to run ...') as halo:
        _hints  = f'[[{counter:06d}]] Main: {recorder_param}; Aux: {eva_params}: %s'
        _params = [ PARAM_ENCODE(*recorder_param) ] + [PARAM_ENCODE(*x) for x in eva_params]
        _params = [ '%05d'%x for x in _params]
        _prefix = '-'.join(_params)

        # check redundancy
        if not IS_REDUNDANT(recorder_conn, _params):
            for trial in range(REPEATED_TIMES):
                _t_hints = _hints%( f'({trial+1}-th) %s' )
                ##
                halo.text = _t_hints%('Execute iPerf3 on Interference Clients ...')
                eva_stdin = []
                for idx, (e_conn, e_param) in enumerate(zip(eva_conns, eva_params)):
                    _bw, _tos = e_param
                    if _bw!=0: #bw==0 means no interference set
                        _port = EVA_PORTS[idx]
                        eva_command = f'iperf3 -c {IPERF3_SERVER} -p {_port} -t 300 -u -b {_bw}M --tos {_tos}'
                        _stdin,_,_ = e_conn.exec_command(eva_command, get_pty=True)
                        eva_stdin.append(_stdin)
                ##
                halo.text = _t_hints%('Execute Recorder on Target Machine ...')
                _bw, _tos = recorder_param
                if _bw!=0:
                    main_command = f'iperf3 -c {IPERF3_SERVER} -t 300 -u -b {_bw}M --tos {_tos}'
                    _filename    = f'{_prefix}-{trial}'
                    recorder_stdin,_stdout,_ = recorder_conn.exec_command(
                        # main_command, get_pty=True
                        f'/home/{RECORDER_USER}/pytrace/my_analyze.py "{main_command}" "{_filename}"', get_pty=True
                    )
                    ## wait for recorder start
                    halo.text = _t_hints%(f'Waiting for start ...')
                    time.sleep(3.2)
                    ## recording
                    for _time in range(REPEATED_DURATION):
                        halo.text = _t_hints%(f'Recording, {REPEATED_DURATION-_time} seconds left ...')
                        time.sleep(1.0)
                    Send_SIGINT(-1, recorder_stdin) # send SIGINT
                    ##  wait for record save
                    halo.text = _t_hints%(f'Processing ...')
                    time.sleep(6.0)
                    pass
                ##
                halo.text = _hints%('Stop Iperf3 on Interference Clients ...')
                for _idx,_stdin in enumerate(eva_stdin):
                    Send_SIGINT(_idx, _stdin)
                time.sleep(1.5) #wait for status sync
            ## touch flag file as checkpoint
            Execute(recorder_conn, f'touch pytrace-logs/{_prefix}.flag')
            if _bw!=0:
                counter += 1
                halo.succeed(_prefix)
            else:
                halo.info(_prefix)
            pass

        ## update parameters for next round
        recorder_param = (200, recorder_param[1])
        recorder_param, eva_params = NEXT_ALL_PARAMS(recorder_param, eva_params)
        recorder_param = (2, recorder_param[1]) #fixed: (2Mbps, ToS)
        pass
