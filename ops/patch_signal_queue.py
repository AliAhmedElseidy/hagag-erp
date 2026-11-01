"""Generate a reversible I/O fairness patch for the audited libsignal 6.0.0 queue only."""
import argparse
import hashlib
from pathlib import Path

BASE_SHA256 = 'd581518bab0da98ddc71cd6616bab769e0de413ec007454b7d42804ee3f244f3'


def patch_queue(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise ValueError('Unreviewed libsignal queue version; refusing to patch')
    before = b'''            } catch(e) {
                job.reject(e);
            }
        }
        if (limit < queue.length)'''
    after = b'''            } catch(e) {
                job.reject(e);
            }
            // Preserve per-device FIFO and completed persistence, but do not
            // starve network I/O with a continuous chain of crypto microtasks.
            await new Promise(resolve => setImmediate(resolve));
        }
        if (limit < queue.length)'''
    if source.count(before) != 1:
        raise ValueError('Queue implementation does not match the reviewed patch')
    return source.replace(before, after)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        raise ValueError('Write a separate candidate; never overwrite an installed dependency in place')
    result = patch_queue(args.source.read_bytes())
    args.output.write_bytes(result)
    print('Generated reviewed libsignal queue fairness patch; cryptography and auth files untouched')
