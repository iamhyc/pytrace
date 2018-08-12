#!/usr/bin/python3
import argparse
import queue, threading
from subprocess import Popen, PIPE as SP_PIPE

TMP_FILE='/tmp/pytrace-tmp.dat'

def main(args):
    events = [('-e', x) for x in args.events]
    events = [x for xs in events for x in xs]
    cmdl = ['trace-cmd', 'record'] + events + ['-o', TMP_FILE]
    result = list()

    with Popen(cmdl, stdout=SP_PIPE) as proc:
        input('[Recording] press ENTER to stop...')
        proc.terminate()
        pass
    
    with Popen(['trace-cmd', 'report', TMP_FILE], stdout=SP_PIPE) as proc:
        for line in proc.stdout.readlines():
            tmp = line.split(maxsplit=4)
            if len(tmp) == 5:
                tmp[2] = float(tmp[2][:-1]) #get float timestamp
                tmp[3] = tmp[3][:-1] # remove column
                result.append(tuple(tmp))
                pass
            pass
        pass

    if args.delta_flag:
        for x in range(1, len(result)):
            print( '%f %f'%(result[x-1][2], result[x][2]-result[x-1][2]) )
        pass
    
    if args.show_flag:
        print('Not implement yet...')
        return

    pass

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(
            description='A customed python wrapper for trace-cmd.')
        parser.add_argument('events', nargs='+', type=str,
            help='events to be traced.')
        parser.add_argument('--delta', dest='delta_flag', action='store_true', default=False,
            help='analyze delta time between events, and output.')
        parser.add_argument('--show', dest='show_flag', action='store_true', default=False,
            help='analyze output with kernelshark.')
        args = parser.parse_args()

        main(args)
    except Exception as e:
        print(e)
    finally:
        exit()