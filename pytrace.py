#!/usr/bin/python3
import argparse
import queue, threading
from subprocess import Popen, PIPE as SP_PIPE

TMP_FILE='/tmp/pytrace-tmp.dat'

def main(args):
    events = [('-e', x) for x in args.events]
    cmdl = ['trace-cmd'] + events + ['-o', TMP_FILE]

    with Popen(cmdl, stdout=PIPE, stderr=PIPE) as proc:
        pass
        
    # with open(TMP_FILE, 'r') as fd:
    #     pass
    pass

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(
            description='A customed python wrapper for trace-cmd.')
        parser.add_argument('events', nargs='+', type=str,
            help='events to be traced.')
        parser.add_argument('--delta', dest='delta_flag', action='store_true', default=True,
            help='analyze delta time between events, and output.')
        args = parser.parse_args()

        main(args)
    except Exception as e:
        print(e)
    finally:
        exit()