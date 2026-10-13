"""Off-device reader/writer load check using a disposable database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.common import Store,iso,utcnow
from tools.seed_demo_data import seed_demo_data


def main(seconds=60, rate=20):
    with TemporaryDirectory(prefix='sentinel-load-') as directory:
        store=Store(seed_demo_data(Path(directory)/'load.db'))
        stop=Event()
        start=monotonic()
        def write():
            count=0
            while monotonic()-start<seconds:
                with store.connection(write=True) as conn:
                    conn.execute('INSERT INTO events (timestamp,node_id,sensor,status,severity,message) VALUES (?,?,?,?,?,?)',
                        (iso(utcnow()),'test','entry_monitor','motion_no_person','info','Load test'))
                count+=1
                stop.wait(max(0,start+count/rate-monotonic()))
            stop.set()
            return count
        def read():
            count=0
            while not stop.is_set():
                store.rows('SELECT * FROM events ORDER BY id DESC LIMIT 200')
                count+=1
                stop.wait(.05)
            return count
        with ThreadPoolExecutor(max_workers=4) as pool:
            producer=pool.submit(write)
            consumers=[pool.submit(read) for _ in range(3)]
            writes=producer.result()
            reads=sum(f.result() for f in consumers)
        print(f'{writes} writes, {reads} reads in {seconds}s; no SQLite lock errors. Disposable DB removed on exit.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=60)
    args=parser.parse_args()
    if not 1<=args.seconds<=300:parser.error('seconds must be 1 to 300')
    main(args.seconds)
