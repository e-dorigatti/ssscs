"""
Generates a random directed graph; The number of outbound edges per node is
distributed normally.
The graph is saved in a file with the following format:
  <number of nodes>\n
  <number of edges>\n
  one row for each edge u-->v: u<space>v
"""

import click
import random
import multiprocessing as mp
import signal
import sys


def worker_process(in_queue, out_queue, num_nodes):
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    pack = in_queue.get()
    while pack is not None:
        node, num_edges = pack
        edges = random.sample(range(num_nodes), num_edges)
        if edges:
            out_queue.put('\n'.join('%d %d' % (node, v) for v in edges))
        pack = in_queue.get()


def writer_process(in_queue, fp):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    anim = ['\\', '|', '/', '-']

    i = 0
    row = in_queue.get()
    while row is not None:
        fp.write(row)
        fp.write('\n')
        i += 1
        if i % 100 == 0:
            sys.stderr.write('  %d Nodes processed\r' % i)
        if i % (len(anim) + 1) == 0:
            sys.stderr.write('%s\r' % anim[i % len(anim)])
        row = in_queue.get()
    fp.flush()


@click.command()
@click.argument('out-file', type=click.File('w'))
@click.option('--nodes', '-n', default=10, help='How many nodes the graph will have')
@click.option('--degree-avg', '-d', default=4,
              help='Average value of outbout edges per node')
@click.option('--degree-stdev', '-D', default=1,
              help='Standard deviation of outbound edge count per node')
@click.option('--processes', '-p', default=mp.cpu_count(),
              help='How many processes to use to generate the graph')
def main(out_file, nodes, degree_avg, degree_stdev, processes):
    """
    Generates a random directed graph. The number of outbound edges per node
    is distributed normally.
    """
    print 'Generating edge counts...'
    edges = [max(0, min(nodes, int(random.normalvariate(degree_avg, degree_stdev))))
             for _ in range(nodes)]
    print 'Graph will have %d edges' % sum(edges)
    out_file.write('%d\n%d\n' % (nodes, sum(edges)))
    out_file.flush()

    # using a small queue so that interrupt signal are received quickly
    in_queue, out_queue = mp.Queue(10), mp.Queue()
    processes = [mp.Process(target=worker_process, args=(in_queue, out_queue, nodes))
                 for _ in range(processes)]
    processes.append(mp.Process(target=writer_process, args=(out_queue, out_file)))
    [p.start() for p in processes]

    try:
        for node, num_edges in enumerate(edges):
            in_queue.put((node, num_edges))
    except KeyboardInterrupt:
        pass

    [in_queue.put(None) for _ in processes]
    [p.join() for p in processes[:-1]]

    out_queue.put(None)
    processes[-1].join()


if __name__ == '__main__':
    main()
