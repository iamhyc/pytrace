#!/usr/bin/python3
import argparse
import queue, threading
from subprocess import Popen, PIPE as SP_PIPE

TMP_FILE='/tmp/pytrace-tmp.dat'

def main(args):
    events = [('-e', x) for x in args.events]
    events = [x for xs in events for x in xs]
    cmdl = ['trace-cmd', 'record'] + events + ['-o', TMP_FILE]

    with Popen(cmdl, stdout=SP_PIPE) as proc:
        input('[Recording] press ENTER to stop...')
        proc.terminate()
        pass
    
    with Popen(['trace-cmd', 'report', TMP_FILE], stdout=SP_PIPE) as proc:
        print(proc.stdout.read())
        pass
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