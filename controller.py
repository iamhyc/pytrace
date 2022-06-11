#!/usr/bin/env python3
import os, sys, time
from halo import Halo
from paramiko import SSHClient
import subprocess as sp

REPEATED_TIMES    = 3
REPEATED_DURATION = 30

IPERF3_SERVER = '127.0.0.1'
IPERF3_PORTS  = [5202, 5203, 5204]

RECORDER_ADDR = '127.0.0.1'
RECORDER_USER = 'lab525'
RECORDER_PWD  = 'lablab'
EVA_CLIENTS  = {
    '127.0.0.1': {'username': 'lab525'},
    # '10.42.0.2': {'username': 'lab525'},
    # '10.42.0.3': {'username': 'lab525'},
}

##
SHELL_RUN = lambda x: sp.run(x, stdout=sp.PIPE, stderr=sp.PIPE, check=True, shell=True)
TOS_SET = [0, 32, 128, 192]
BW_SET  = list(range(0, 105, 5))

PARAM_ENCODE = lambda bw,tos: (bw<<8)|(tos)
PARAM_DECODE = lambda _code: (_code>>8, _code&0xFF)
BEGIN_PARAM  = ( min(BW_SET), min(TOS_SET) )
END_PARAM    = ( max(BW_SET), max(TOS_SET) )
IS_ENDED     = lambda param: param==END_PARAM

def NEXT_PARAM(param):
    _bw, _tos = param
    if _bw != BW_SET[-1]:
        _bw = BW_SET[ BW_SET.index(_bw)+1]
    elif _tos != TOS_SET[-1]:
        _bw = 0
        _tos = TOS_SET[ TOS_SET.index(_tos)+1 ]
    return (_bw, _tos)

def NEXT_ALL_PARAMS(r_params, e_params):
    all_params = [r_params] + e_params
    for _idx,_param in enumerate(all_params):
        if IS_ENDED( _param ):
            all_params[_idx] = BEGIN_PARAM
            continue
        else:
            all_params[_idx] = NEXT_PARAM(_param)
            return all_params[0], all_params[1:]
    return (r_params, None)
##
def Execute(conn, cmd):
    _, stdout, stderr = conn.exec_command(cmd)
    output = stdout.read()
    error = stderr.read()
    if error:
        raise Exception(error)
    else:
        return output
def Send_SIGINT(stdin):
    stdin.write( chr(3) )
    stdin.flush()
    pass


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
Execute(recorder_conn, f'mkdir -p pytrace-logs')
Execute(recorder_conn, f'echo {RECORDER_PWD} | sudo -S echo')

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
    r_param, *e_params = sys.argv[1].split('-')
    recorder_param = PARAM_DECODE(r_param)
    eva_params = [ PARAM_DECODE(_param) for _param in e_params ]
else:
    recorder_param = BEGIN_PARAM
    eva_params = [ BEGIN_PARAM for _ in EVA_CLIENTS ]

## Execute Remote Control
counter = 0
with Halo('Ready to run ...') as halo:
    while eva_params is not None:
        _hints  = f'[[{counter:06d}]] Main: {recorder_param}; Aux: {eva_params}: %s'
        _params = [ str(PARAM_ENCODE(*recorder_param)) ] + [str(PARAM_ENCODE(*x)) for x in eva_params]
        _prefix = '-'.join(_params)
        # check redundancy
        if Execute(recorder_conn, f'ls pytrace-logs/{_prefix}.flag'):
            continue
        

        for trial in range(REPEATED_TIMES):
            _hints = _hints%( f'({trial}-th Trial) %s' )
            ##
            halo.text = _hints%('Execute Iperf3 on Interference Clients ...')
            eva_stdin = []
            for idx, (e_conn, e_param) in enumerate(zip(eva_conns, eva_params)):
                _bw, _tos = e_param
                if _bw!=0: #bw==0 means no interference set
                    _port = IPERF3_PORTS[idx]
                    eva_command = f'iperf3 -c {IPERF3_SERVER} -p {_port} -t 300 -u -b {_bw} --tos {_tos}'
                    _stdin,_,_ = e_conn.exec_command(eva_command)
                    eva_stdin.append(_stdin)
            ##
            halo.text = _hints%('Execute Recorder on Target Machine ...')
            _bw, _tos = recorder_param
            if _bw!=0:
                counter += 1
                main_command = f'iperf3 -c {IPERF3_SERVER} -t 300 -u -b {_bw} --tos {_tos}'
                recorder_stdin,_,_ = recorder_conn.exec_command(
                    f'python3 /home/lab525/pytrace/my_analyze.py {main_command}'
                )
                ## wait for recorder start
                time.sleep(3.2)
                halo.text = _hints%(f'Waiting for start ...')
                ## recording
                for _time in range(REPEATED_DURATION):
                    halo.text = _hints%(f'Recording, {REPEATED_DURATION-_time} seconds left ...')
                    time.sleep(1.0)
                Send_SIGINT(recorder_stdin) # send SIGINT
                ##  wait for record save
                halo.text = _hints%(f'Processing ...')
                time.sleep(5.2)
                pass
            ##
            halo.text = _hints%('Stop Iperf3 on Interference Clients ...')
            for _stdin in eva_stdin:
                Send_SIGINT(_stdin)
        ## touch flag file as checkpoint
        Execute(recorder_conn, f'touch pytrace-logs/{_prefix}.flag')
        if _bw!=0:
            halo.succeed(_prefix)


        ## update parameters for next round
        recorder_param, eva_params = NEXT_ALL_PARAMS(recorder_param, eva_params)
        pass
