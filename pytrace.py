#!/usr/bin/python3
import sys, time, signal, threading, argparse
import queue, threading
from subprocess import Popen, PIPE as SP_PIPE

TMP_FILE='/tmp/data-pytrace.dat'

def startThread(target, args=()):
    args = tuple(args)
    t = threading.Thread(target=target, args=args)
    t.setDaemon(True)
    t.start()
    return t

def execThread(proc_cmdl, q):
    if not proc_cmdl: return
    
    with Popen(proc_cmdl.split(), stderr=SP_PIPE) as proc:
        q.get() #block here
        proc.terminate()
        pass
    pass

def recordProcedure(args):
    q = queue.Queue()
    events = [('-e', x) for x in args.events]
    events = [x for xs in events for x in xs]
    cmdl = ['trace-cmd', 'record'] + events + ['-s', '100', '-o', TMP_FILE]

    with Popen(cmdl, stdout=SP_PIPE, stderr=SP_PIPE) as proc:
        print('============ Initializing, Please Wait ============\n')
        time.sleep(3.0)

        t = startThread(execThread, args=(args.exec_proc, q))
        input('========== Recording, press ENTER to stop ==========\n')
        proc.send_signal(signal.SIGINT)
        q.put_nowait('exit')

        print('============= Processing, Please Wait =============\n')
        time.sleep(5.0)
        pass
    
    pass

def main(args):
    result = list()
    file_name = '+'.join(args.events)

    if not args.strike_flag:
        recordProcedure(args)

    with Popen(['trace-cmd', 'report', TMP_FILE], stdout=SP_PIPE) as proc:
        for line in proc.stdout.readlines():
            tmp = line.split(maxsplit=4)
            if len(tmp)==5 and (args.filter in tmp[4].decode()): #TODO: impl. regex for filter
                tmp[2] = float(tmp[2][:-1]) #get float timestamp
                tmp[3] = tmp[3][:-1] #remove column
                result.append(tuple(tmp))
                pass
            pass
        pass

    if len(result) != 0:
        with open(file_name+'.log', 'w+') as fd:
            if args.output_flag:
                [fd.write('%f\n'%x[2]) for x in result]
                pass
            elif args.delta_flag:
                for x in range(1, len(result)):
                    fd.write('%f %f\n'%(result[x-1][2], result[x][2]-result[x-1][2]))
                pass
            else: #vomit on the console
                [print('%s %s %.6f %s %s'%(
                    x[0].decode(), x[1].decode(), x[2], x[3].decode(), x[4].decode())) for x in result]
                pass
            pass
        pass

    if args.show_flag:
        Popen(['kernelshark', '-i', TMP_FILE])
        return

    pass

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(
            description='A customed python wrapper for trace-cmd.')
        parser.add_argument('events', nargs='+', type=str,
            help='events to be traced.')
        parser.add_argument('--exec', dest='exec_proc', default='',
            help='execute process when recording begins.')
        parser.add_argument('--filter', dest='filter', type=str, default='',
            help='filter the captured events by info section.')
        parser.add_argument('--redo', dest='strike_flag', action='store_true', default=False,
            help='use the last recorded data.')
        parser.add_argument('--output', dest='output_flag', action='store_true', default=False,
            help='output the raw timestamp data.')
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