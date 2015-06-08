"""
http://en.wikipedia.org/wiki/Proof-of-work_system

For example:

$ python pof.py 4 -s 'ciao-' -S 30 2>/dev/null
zpfljbbqgamhdzhjcgekmaxyaxltys
000089f0f44053222c9145f64cbfb5174d097a57

In [44]: hashlib.sha1('ciao-zpfljbbqgamhdzhjcgekmaxyaxltys').hexdigest()
Out[44]: '000089f0f44053222c9145f64cbfb5174d097a57'
"""

import hashlib
import random
import multiprocessing as mp
import click
from os import sys
import time
import Queue


def hash_generator(s, n):
    def wrapped():
        a = 'abcdefghijklmnopqrstuvwxyz0123456789'
        while True:
            content = reduce(lambda x, y: x + random.choice(a), range(n), '')
            yield content, hashlib.sha1(s + content).hexdigest()
    return wrapped


def pof(i, generator, result):
    best, start = 0, time.time()
    try:
        for n, (append, hash) in enumerate(generator()):
            zeroes = 0
            while zeroes < len(hash) and hash[zeroes] == '0':
                zeroes += 1
        
            if zeroes > best:
                result.put((append, hash, zeroes))
                best = zeroes
    except KeyboardInterrupt:
        pass

    duration = time.time() - start
    print >> sys.stderr, 'Process %d: tried %d hashes in %.2f seconds (%.2f hash/s)' % (
                          i, n, duration, n / duration)


@click.command()
@click.argument('num-zeroes', type=int)
@click.option('-p', '--processes', default=mp.cpu_count())
@click.option('-s', '--base-string', default='')
@click.option('-S', '--string-size', default=50)
def main(num_zeroes, processes, string_size, base_string):
    result = mp.Manager().Queue()
    generator = hash_generator(base_string, string_size)
    processes = [mp.Process(target=pof, args=(i, generator, result))
                 for i in range(processes)]
    [p.start() for p in processes]

    append, hash, best = '', '', 0
    try:
        while best < num_zeroes:
            a, h, z = result.get()
            if z > best:
                num = int(24. * z / num_zeroes)
                print >> sys.stderr, h, a, '|' + '-' * num + '>' +  ' ' * (25 - num) + '|'
                append, hash, best = a, h, z
    except KeyboardInterrupt:
        pass

    print append
    print hash
    sys.exit(best != num_zeroes)


if __name__ == '__main__':
    main()
