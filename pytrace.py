#!/usr/bin/python3
import os, re, time, signal
import argparse
import subprocess as sp
from pathlib import Path
from termcolor import cprint

TMP_FILE = '/tmp/pytrace-%s.dat'%( time.strftime('%Y%m%d-%H%M%S') )
TRACE_SLOT_US = 500 #default as 1000us, i.e., 1ms.

SHELL_RUN  = lambda x: sp.run(x, stdout=sp.PIPE, stderr=sp.PIPE, check=True, shell=True)
TRACE_ITEM = re.compile( '\s+(\S+)\s+\[(\d+)\] (\d+\.\d+):\s+(\S+):\s+(.+)' )
#                            [task,    cpu,    timestamp,    event,   info]

def record_events(events, exec_cmd=None):
    events = [['-e', x] for x in events]
    events = sum(events,[]) #flatten
    trace_cmd = ['trace-cmd', 'record', '-s', str(TRACE_SLOT_US), '-o', TMP_FILE] + events
    if os.geteuid() != 0:
        trace_cmd = ['sudo'] + trace_cmd
        SHELL_RUN('sudo echo')

    ## start trace-cmd and wait for initialized
    trace_proc = sp.Popen(trace_cmd, stdout=sp.PIPE, stderr=sp.PIPE)
    cprint('Initializing, Please Wait ...\n', 'green')
    time.sleep(2.0)

    ## execute at the same time
    if exec_cmd:
        exec_proc = sp.Popen(exec_cmd, shell=True)

    ## hook SIGINT signal
    def signal_handler(sig, frame):
        try:
            trace_proc.send_signal(signal.SIGINT)
            exec_proc.terminate()
        except:
            pass
        cprint('\nProcessing, Please Wait ...', 'green')
        time.sleep(5.0)
        pass
    signal.signal(signal.SIGINT, signal_handler)
    
    ## wait until trace terminated
    trace_proc.wait()
    return TMP_FILE

def filter_events(trace_file, filters):
    raw_records    = SHELL_RUN( f'trace-cmd report -i {trace_file}' ).stdout.decode()
    cooked_records = TRACE_ITEM.findall(raw_records)

    if not filters:
        return cooked_records

    results = {name:[] for name in filters}
    for item in cooked_records:
        for name in filters:
            if name in item[-1]:
                print(item)
                results[name].append( item )
        pass

    return results

def analyze(events):
    pass

def main(args):
    ## get trace file, w/ program executed at same time
    if args.command=='record':
        _file = record_events(args.events, args.exec)
    elif args.command=='replay':
        if args.trace_file:
            _file = args.trace_file
        else:
            _all  = sorted( Path('/tmp').glob('pytrace-*.dat') )
            _file = _all[-1] #the last trace file
    else:
        return

    ## filter the recorded events
    events = filter_events(_file, args.filters)

    ## customized analysis
    analyze(events)

    pass

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(
                                description='A customized python wrapper for trace-cmd.')
        subparsers = parser.add_subparsers(dest='command')
        ##
        p_record = subparsers.add_parser('record', help='record new events to analyze.')
        p_record.add_argument('events', nargs='+', type=str,
                                help='events to be traced.')
        p_record.add_argument('--exec', dest='exec', default='',
                                help='execute process when recording begins.')
        p_record.add_argument('--filter', dest='filters', nargs='*', type=str,
                                help='filter the captured events by info section.')
        ##
        p_replay = subparsers.add_parser('replay', help='replay existing trace file to analyze.')
        p_replay.add_argument('trace_file', nargs='?', type=str,
                                help='events to be traced.')
        p_replay.add_argument('--filter', dest='filters', nargs='*', type=str,
                                help='filter the captured events by info section.')

        args = parser.parse_args()
        main(args)
    except Exception as e:
        raise e
    finally:
        pass
