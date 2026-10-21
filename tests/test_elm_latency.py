import math
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import elm_radio
from elm_radio import connections
from gauge_sdl import responsive_approach


class LatencyTests(unittest.TestCase):
    def test_connected_peer_parser_ignores_classic_and_other_fields(self):
        text='Connections:\n < LE 02:00:00:00:00:05 handle 10 state 1 lm CENTRAL\n > LE 02:00:00:00:00:02 handle 11 state 1 lm PERIPHERAL\n < ACL 02:00:00:00:00:06 handle 3 state 1'
        self.assertEqual(connections(text),{('02:00:00:00:00:05',10),('02:00:00:00:00:02',11)})

    def test_large_change_settles_at_low_and_high_fps(self):
        for fps in (20,60):
            value=0
            for _ in range(round(.15*fps)):
                value=responsive_approach(value,6000,150,1/fps)
            self.assertGreater(value,5800)
            self.assertLessEqual(value,6000)

    def test_small_changes_still_snap_and_missing_stays_missing(self):
        self.assertEqual(responsive_approach(1000,1100,150,1/60),1100)
        self.assertTrue(math.isnan(responsive_approach(1000,math.nan,150,.02)))
        self.assertEqual(responsive_approach(math.nan,1100,150,.02),1100)


class RadioTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_gateway_peers_are_tuned(self):
        updates=[]
        async def run(*args):
            if args==('hcitool','con'):
                return 0, (' < LE 02:00:00:00:00:05 handle 10 state 1\n'
                           ' > LE 02:00:00:00:00:02 handle 11 state 1\n'
                           ' < LE 02:00:00:00:00:06 handle 12 state 1'), ''
            updates.append(args)
            return 0,'',''
        with patch.object(elm_radio,'command',side_effect=run), patch.object(elm_radio.asyncio,'sleep',new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await elm_radio.maintain_low_latency(SimpleNamespace(upstream_address='02:00:00:00:00:05'),
                                                     '02:00:00:00:00:02',Mock())
        self.assertEqual({args[3] for args in updates},{'10','11'})


if __name__=='__main__': unittest.main()
