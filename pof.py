"""
http://en.wikipedia.org/wiki/Proof-of-work_system

Generates a string which, when hashed, starts with at least n zero bits
For example:

$ python pof.py 8 -s 'ciao-' -S 30 -a sha1 2>/dev/null
eMloHwJPCCtfW9Co8zDZWsdcgUrrMh
007673eefcadc7aa71887a284ec52b1a53020d44

In [44]: hashlib.sha1('ciao-eMloHwJPCCtfW9Co8zDZWsdcgUrrMh').hexdigest()
Out[44]: '007673eefcadc7aa71887a284ec52b1a53020d44'
"""

import hashlib
import random
import multiprocessing as mp
import click
from os import sys
import time
import Queue


def hash_generator(base, length, algorithm):
    hash_function = getattr(hashlib, algorithm)
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

    def wrapped():
        while True:
            content = reduce(lambda x, y: x + random.choice(alphabet), range(length), '')
            yield content, hash_function(base + content).hexdigest()
    return wrapped


def pof(i, generator, result, stop):
    best, start = 'f', time.time()
    try:
        for n, (append, hash) in enumerate(generator()):
            if hash < best:
                result.put((append, hash))
                best = hash

            if n % 1000 == 0:
                try:
                    _ = stop.get_nowait()
                except Queue.Empty:
                    pass
                else:
                    break
    except KeyboardInterrupt:
        pass

    duration = time.time() - start
    print >> sys.stderr, 'Process %d: tried %d hashes in %.2f seconds (%.2f hash/s)' % (
                          i, n, duration, n / duration)


def num_zeroes_prefix(h):
    zeroes = [4, 3] + [2]*2 + [1]*4 + [0]*8

    z = 0
    while z < len(h) and h[z] == '0':
        z += 1
    return 4 * z + (zeroes[int(h[z], 16)] if z < len(h) else 0)


@click.command()
@click.argument('num-zeroes', type=int)
@click.option('-p', '--processes', default=mp.cpu_count())
@click.option('-s', '--base-string', default='')
@click.option('-S', '--string-size', default=50)
@click.option('-a', '--algorithm', default='sha1', type=click.Choice(hashlib.algorithms))
def main(num_zeroes, processes, string_size, base_string, algorithm):
    manager = mp.Manager()
    result, stop = manager.Queue(), manager.Queue()
    generator = hash_generator(base_string, string_size, algorithm)
    processes = [mp.Process(target=pof, args=(i, generator, result, stop))
                 for i in range(processes)]
    [p.start() for p in processes]

    append, hash, best = '', 'f', 0
    try:
        while best < num_zeroes:
            a, h = result.get()

            if h < hash:
                z = num_zeroes_prefix(h)
                num = int(24. * z / num_zeroes)
                print >> sys.stderr, h, a, '|' + '-' * num + '>' + ' ' * (25 - num) + '|'

                append, hash, best = a, h, z
    except KeyboardInterrupt:
        pass
    else:
        [stop.put(1) for _ in processes]
        [p.join() for p in processes]

    print append
    print hash
    sys.exit(best != num_zeroes)


if __name__ == '__main__':
    main()
