import unittest
from elm327_demo import Elm327Demo


class DemoTests(unittest.TestCase):
    def test_fragmented_init_echo_and_prompt(self):
        sim = Elm327Demo(lambda: 0)
        self.assertEqual(sim.feed(b'AT'), [])
        self.assertIn(b'ELM327', sim.feed(b'Z\r')[0])
        self.assertEqual(sim.feed(b'ATE0\r'), [b'OK\r>'])
        self.assertEqual(sim.feed(b'ATS0\r010C\r')[-1], b'410C0E10\r>')

    def test_dynamic_rpm_and_speed(self):
        now = [0]
        sim = Elm327Demo(lambda: now[0])
        low = sim.values()
        now[0] = 6
        high = sim.values()
        self.assertEqual((low['rpm'], high['rpm']), (900, 4500))
        self.assertEqual((low['speed'], high['speed']), (15, 85))

    def test_headers_and_no_spaces(self):
        sim = Elm327Demo(lambda: 0)
        sim.feed(b'ATE0\rATH1\rATS0\rATSH7E0\r')
        self.assertEqual(sim.feed(b'010C\r'), [b'7E804410C0E10\r>'])

    def test_unknown_private_pid_is_not_invented(self):
        sim = Elm327Demo(lambda: 0)
        self.assertIn(b'NO DATA', sim.feed(b'22FFFF\r')[0])

    def test_unknown_at_is_not_claimed_supported(self):
        sim = Elm327Demo(lambda: 0)
        self.assertIn(b'?', sim.feed(b'ATUNKNOWN\r')[0])

    def test_empty_command_repeats_previous(self):
        sim = Elm327Demo(lambda: 0)
        sim.feed(b'ATE0\r')
        expected = sim.feed(b'010D\r')
        self.assertEqual(sim.feed(b'\r'), expected)


if __name__ == '__main__':
    unittest.main()
