import asyncio
import unittest
from price_engine.scheduler import PollingScheduler
from price_engine.adapters import Listing


def listing(n):
    return Listing(str(n),'fixture',str(n),f'https://example.org/{n}','p')


class SchedulerTests(unittest.TestCase):
    def test_bounded_queue_deduplication_errors_and_shutdown(self):
        async def run():
            done=asyncio.Event()
            started=asyncio.Event()
            active=set()
            max_active=[0]
            checked=[]
            async def fake_poll(item):
                self.assertNotIn(item.listing_id,active)
                active.add(item.listing_id)
                max_active[0]=max(max_active[0],len(active))
                started.set()
                try:
                    if item.listing_id=='bad': raise ValueError('fixture fault')
                    await done.wait()
                    checked.append(item.listing_id)
                finally:
                    active.discard(item.listing_id)
                return None
            scheduler=PollingScheduler(fake_poll,interval_seconds=0.01,
                workers=2,max_queued=2,jitter=lambda a,b:1.0)
            await scheduler.start()
            first=listing(1)
            self.assertTrue(scheduler.enqueue(first))
            self.assertFalse(scheduler.enqueue(first))
            await asyncio.wait_for(started.wait(),1)
            self.assertTrue(scheduler.enqueue(listing('bad')))
            self.assertTrue(scheduler.enqueue(listing(2)))
            self.assertFalse(scheduler.enqueue(listing(3)))
            scheduler.schedule_periodic([first])
            await asyncio.sleep(0.02)
            done.set()
            await asyncio.wait_for(scheduler.close(),3)
            self.assertIn('1',checked)
            self.assertIn('2',checked)
            self.assertEqual(scheduler.last_error.get('bad'),'ValueError')
            self.assertLessEqual(max_active[0],2)
            self.assertEqual(scheduler.queue.qsize(),0)
            self.assertFalse(scheduler._pending)
        asyncio.run(asyncio.wait_for(run(),5))

if __name__=='__main__': unittest.main()
