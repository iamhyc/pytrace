#!/usr/bin/env python3
import re
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

## `iwlwifi/mvm/tx.c`: iwl_mvm_tx_mpdu
# "TX to [%d|%d] Q:%d - seq: 0x%x len %d"
tx_begin_filter  = 'TX to ['
tx_begin_extract = re.compile('TX to \[\d+\|\d+\] Q:\d+ - seq: (0x\S+) len (\d+)')
#                                                              [ssn,       skb_len]

## `iwlwifi/queue/tx.c`: iwl_txq_reclaim
# "[Q %d] %d -> %d (%d)"
tx_end_filter    = ' -> '
tx_end_extract   = re.compile('\[Q \S+\] (\S+) -> (\S+) \(\S+\)')
#                                        [s_seq,  t_seq]

## `iwlwifi/mvm/tx.c`: iwl_mvm_rx_tx_cmd -> iwl_mvm_rx_tx_cmd_single
# "\t\t\t\tinitial_rate 0x%x retries %d, idx=%d ssn=%d next_reclaimed=0x%x seq_ctl=0x%x"
tx_ack_filter  = 'initial_rate 0x'
tx_ack_extract = re.compile('\s*initial_rate 0x\S+ retries \d+, idx=(\d+) ssn=\d+ next_reclaimed=0x\S+ seq_ctl=(0x\S+)')
#                                                                   [idx,                                      seq]


## ================================================ ##
RECORD_FLAG = True
COMMAND     = 'iperf3 -c 10.42.0.1 -u -b 100K -t 30'

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
        ssn, skb_len = tx_begin_extract.findall(_info)[0]
        ssn          = int(ssn, 16)
        tx_begin.append( (ssn, _time) )
    ## extract `tx_end`
    tx_end   = []
    for item in records[tx_end_filter]:
        item = parse(item)
        _time, _info = item['timestamp'], item['info']
        idx, seq     = tx_end_extract.findall(_info)[0]
        ssn          = IEEE80211_SEQ_TO_SN( int(seq, 16) )
        tx_end.append( (ssn, _time) )

    ## match the beginning of two records
    print(len(tx_begin), len(tx_end))
    t_idx    = 0 
    while tx_end[t_idx][0] != tx_begin[0][0]:
        t_idx += 1
    ## get tx interval
    results  = []
    retries = []
    for (s_seq, s_time) in tx_begin:
        if t_idx >= len(tx_end):
            break
        elif s_seq == tx_end[t_idx][0]:
            _delta = tx_end[t_idx][1] - s_time
            results.append( (s_time, _delta) )
            t_idx += 1
        else:
            retries.append( (s_seq, s_time) )
            print('Packet 0x%x dropped at %.6f.'%(s_seq, s_time))

    ## get statistics
    _time, _delta = zip(*results)
    _delta = 1000 * np.array(_delta)
    try:
        _, drop_time  = zip(*retries)
    except:
        drop_time = []
    ## plot timeline
    fig, ax = plt.subplots()
    ax.plot(_time, _delta, '-k')
    ax.set_xlabel('Timestamp (s)')
    ax.set_ylabel('Delay (ms)')
    ax_d = ax.twinx()
    ax_d.plot(drop_time, [1]*len(drop_time), 'or')
    # ax_d.set_ylim(1.0, 1.0)
    ax_d.set_ylabel('Drop Rate')
    ## plot CDF
    fig, ax = plt.subplots()
    ax.plot( *get_cdf(_delta) )
    ax.set_xlabel('Delay (ms)')
    ax.set_ylabel('CDF')
    plt.show()
    pass

tx_interval_analyze()
