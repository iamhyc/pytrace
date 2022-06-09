#!/usr/bin/env python3
import re
import time
from itertools import chain
import numba
from numba import prange
import numpy as np
import matplotlib.pyplot as plt
from pytrace import pytrace_replay, pytrace_record
from pytrace import pytrace_parse_item as parse

IEEE80211_SCTL_SEQ  = 0xFFF0
#define IEEE80211_SEQ_TO_SN(seq)	(((seq) & IEEE80211_SCTL_SEQ) >> 4)
IEEE80211_SEQ_TO_SN = lambda seq: (seq&IEEE80211_SCTL_SEQ)>>4
#define IEEE80211_SN_TO_SEQ(ssn)	(((ssn) << 4) & IEEE80211_SCTL_SEQ)
IEEE80211_SN_TO_SEQ = lambda ssn: (ssn<<4)&IEEE80211_SCTL_SEQ

#define QUEUE_TO_SEQ(q)	(((q) & 0x1f) << 8)
QUEUE_TO_SEQ = lambda q: (q&0x1F)<<8
#define INDEX_TO_SEQ(i)	((i) & 0xff)
INDEX_TO_SEQ = lambda i: i&0xFF
#dev_cmd->hdr.sequence = cpu_to_le16( (u16)( QUEUE_TO_SEQ(txq_id)|INDEX_TO_SEQ(idx) ) );
CMD_SEQ      = lambda qid,idx: QUEUE_TO_SEQ(qid)|INDEX_TO_SEQ(idx)

SSN_TO_IDX   = lambda ssn: (ssn&0x00FF)

## `iwlwifi/pcie/rx.c`: iwl_pcie_rx_handle => iwl_pcie_rx_handle_rb
# "Q %d: cmd at offset %d: %s (%.2x.%2x, seq 0x%x)"
hcmd_rx_filter  = ': cmd at offset '
tx_end_extract  = re.compile('Q \d+: cmd at offset \d+: (\S+) \(.+, seq (0x\S+)\)')
#                                                       [cmd,           cmd_seq]

## `iwlwifi/mvm/rxmq.c`: iwl_mvm_get_signal_strength
# "energy In A %d B %d, and max %d"
energy_filter  = 'energy In A '
energy_extract = re.compile("energy In A (\d+) B (\d+), and max \d+")
#                                        [sig_a, sig_b]

## `iwlwifi/pcie/tx.c`: iwl_mvm_tx_mpdu
# "TX to [%d|%d] Q:%d - seq: 0x%x len %d"
tx_begin_filter  = 'TX to ['
tx_begin_extract = re.compile('TX to \[\d+\|\d+\] Q:6 - seq: (0x\S+) len (\d+)')
#                                                            [ssn,       skb_len]

## `iwlwifi/queue/tx.c`: iwl_txq_reclaim
# "[Q %d] %d -> %d (%d)"
tx_end_filter    = ' -> '
tx_end_extract   = re.compile('\[Q 6\] (\d+) -> (\d+) \(\d+\)')
#                                      [s_idx,  t_idx]

## `iwlwifi/mvm/tx.c`: iwl_mvm_rx_tx_cmd -> iwl_mvm_rx_tx_cmd_single
# "\t\t\t\tinitial_rate 0x%x retries %d, idx=%d ssn=%d next_reclaimed=0x%x seq_ctl=0x%x"
tx_ack_filter  = 'initial_rate 0x'
tx_ack_extract = re.compile('\s*initial_rate 0x\S+ retries \d+, idx=(\d+) ssn=\d+ next_reclaimed=0x\S+ seq_ctl=(0x\S+)')
#                                                                   [idx,                                      seq]


## ================================================ ##
RECORD_FLAG = True
COMMAND     = 'iperf3 -c 10.42.0.1 -u -b 3M -t 300 --tos 127'

if RECORD_FLAG:
    records = pytrace_record(events=['iwlwifi_msg'],
                            exec_cmd=COMMAND,
                            filters=[tx_begin_filter, tx_end_filter])
else:
    records = pytrace_replay(filters=[
                energy_filter,
                tx_begin_filter, tx_end_filter
            ])

##

@numba.jit(parallel=True)
def _get_cdf(y, pmf_x):
    pmf_y = np.zeros(len(y))
    #
    for i in prange(1,len(y)):
        pmf_y[i] = np.logical_and( y>=pmf_x[i-1], y<pmf_x[i] ).sum()
    cdf_y = np.cumsum(pmf_y) / len(y)
    return cdf_y

def get_cdf(y):
    pmf_x = np.linspace( 0, np.max(y)*1.001, num=len(y) )
    cdf_y = _get_cdf(y, pmf_x)
    
    return (pmf_x, cdf_y)

def tx_interval_analyze():
    ## extract `tx_begin`
    tx_begin = []
    for item in records[tx_begin_filter]:
        item = parse(item)
        _time, _info = item['timestamp'], item['info']
        try:
            ssn, skb_len = tx_begin_extract.findall(_info)[0]
            s_idx        = SSN_TO_IDX( int(ssn, 16) )
            tx_begin.append( (_time, (0, s_idx, int(skb_len))) )
        except:
            print('==>', _info)
    ## extract `tx_end`
    tx_end   = []
    for item in records[tx_end_filter]:
        item = parse(item)
        _time, _info = item['timestamp'], item['info']
        try:
            s_idx, t_idx = tx_end_extract.findall(_info)[0]
            s_idx, t_idx = int(s_idx), int(t_idx)
            tx_end.append( (_time, (1, s_idx, t_idx) ) )
        except:
            print('<==', _info)

    ##
    tx_timeline = tx_begin + tx_end
    tx_timeline.sort(key=lambda x:x[0])
    acc_pkt = dict()
    acc_pkt_num = np.zeros( len(tx_timeline) )
    acc_pkt_len = np.zeros( len(tx_timeline) )
    avg_delay   = list()
    # print(tx_timeline)
    for tt, (s_time, (_type, *_data)) in enumerate(tx_timeline):
        if _type==0: #push
            s_idx,skb_len = _data
            if s_idx in acc_pkt: #FIXME: mark NOACK
                _,_,_len = acc_pkt.pop(s_idx)
                acc_pkt_len[tt] -= _len
                acc_pkt_num[tt] -= 1
            else:
                acc_pkt[ s_idx ] = (tt,s_time,skb_len)
                acc_pkt_num[tt] = 1
                acc_pkt_len[tt] = skb_len
        elif _type==1: #pop
            s_idx,t_idx = _data
            if s_idx<t_idx:
                IdxRange = range(s_idx, t_idx)
            else:
                IdxRange = chain( range(s_idx, 256), range(t_idx) )
            LenRange = len( list(IdxRange) )
            ##
            for _len,_idx in enumerate(IdxRange):
                if _idx in acc_pkt:
                    _,_time,_  = acc_pkt[_idx]
                    _LenRange = LenRange - _len
                    _delay = (s_time-_time) / _LenRange
                    avg_delay.append( (_time,_delay) )
                    break
            if _idx not in acc_pkt:
                print( s_idx, t_idx, acc_pkt.keys() )
                print()
                pass
            ##
            for _idx in IdxRange:
                try:
                    _tt,_,_len = acc_pkt.pop(_idx)
                    acc_pkt_len[tt] -= _len
                    acc_pkt_num[tt] -= 1
                except: #maybe retries
                    pass
        else:
            print('???')
        pass
    acc_pkt_num = acc_pkt_num.cumsum()
    acc_pkt_len = acc_pkt_len.cumsum()
    ## plot change of accumulated statistics
    # fig, ax = plt.subplots()
    s_times,_ = zip(*tx_timeline)
    # ax.plot(s_times, acc_pkt_num, '-k')
    # # ax.set_ylim(0, 1.1*max(acc_pkt_num))
    # ax.set_ylabel('Number of Packets')
    # ax.legend(['num_pkt'])
    #
    # ax1 = ax.twinx()
    # ax1.plot(_time, acc_pkt_len, '-b')
    # ax1.set_ylabel('Queue Length (byte)')
    #
    # ax2 = ax.twinx()
    avg_times, avg_delay = list(zip(*avg_delay))
    avg_delay = np.array(avg_delay) * 1000
    # ax2.plot( avg_times, avg_delay, 'or' )
    # # ax.set_ylim(0, 1.1*max(avg_times))
    # ax2.set_ylabel('Delay (ms)')

    #
    fig, ax = plt.subplots()
    _name = 'pytrace-%s'%( time.strftime('%Y%m%d-%H%M%S') )
    np.savez(f'logs/{_name}.npz', **{
        'avg_times': avg_times,
        'avg_delay':avg_delay,
        'acc_pkt_num': acc_pkt_num,
        'acc_pkt_len': acc_pkt_len,
        'tx_timeline': tx_timeline
    })
    ax.plot( *get_cdf(avg_delay) )
    ax.set_xlabel('Delay (ms)')
    ax.set_ylabel('CDF')
    plt.show()

    # ## match the beginning of two records
    # print(len(tx_begin), len(tx_end))
    # t_idx    = 0 
    # while tx_end[t_idx][0] != tx_begin[0][0]:
    #     t_idx += 1
    # ## get tx interval
    # results  = []
    # retries = []
    # for (s_seq, s_time) in tx_begin:
    #     if t_idx >= len(tx_end):
    #         break
    #     elif s_seq == tx_end[t_idx][0]:
    #         _delta = tx_end[t_idx][1] - s_time
    #         results.append( (s_time, _delta) )
    #         t_idx += 1
    #     else:
    #         retries.append( (s_seq, s_time) )
    #         print('Packet 0x%x dropped at %.6f.'%(s_seq, s_time))

    # ## get statistics
    # _time, _delta = zip(*results)
    # _delta = 1000 * np.array(_delta)
    # try:
    #     _, drop_time  = zip(*retries)
    # except:
    #     drop_time = []
    # ## plot timeline
    # fig, ax = plt.subplots()
    # ax.plot(_time, _delta, '-k')
    # ax.set_xlabel('Timestamp (s)')
    # ax.set_ylabel('Delay (ms)')
    # ax_d = ax.twinx()
    # ax_d.plot(drop_time, [1]*len(drop_time), 'or')
    # # ax_d.set_ylim(1.0, 1.0)
    # ax_d.set_ylabel('Drop Rate')
    # ## plot CDF
    # fig, ax = plt.subplots()
    # ax.plot( *get_cdf(_delta) )
    # ax.set_xlabel('Delay (ms)')
    # ax.set_ylabel('CDF')
    # plt.show()
    pass

tx_interval_analyze()
