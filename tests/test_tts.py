import importlib.util
import sys
import threading
import unittest
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


with patch.dict(sys.modules, {'RPi': MagicMock(), 'RPi.GPIO': MagicMock(), 'pygame': MagicMock(), 'pyttsx3': MagicMock()}):
    spec = importlib.util.spec_from_file_location('timer_lapper_test', 'timer_lapper.py')
    timer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(timer)


class TtsTests(unittest.TestCase):
    def setUp(self):
        timer.tts_queue = Queue()
        timer.tts_enabled = True
        timer.tts_generation = 0
        timer._tts_thread = None
        timer.btn_tts = MagicMock()
        timer.colPurple = 'purple'
        timer.colFg1 = 'grey'
        timer.race_winner = None

    def test_disable_discards_pending_and_reenable_accepts_new_speech(self):
        started = threading.Event()
        release = threading.Event()
        spoken = []
        engine = MagicMock()
        engine.say.side_effect = spoken.append
        engine.runAndWait.side_effect = lambda: (started.set(), release.wait(2))
        with patch.object(timer.pyttsx3, 'init', return_value=engine):
            timer.speak('first')
            self.assertTrue(started.wait(2))
            timer.speak('stale')
            timer.ToggleTTS()
            timer.speak('disabled')
            timer.ToggleTTS()
            timer.speak('new')
            release.set()
            timer.tts_queue.put(None)
            timer._tts_thread.join(2)
        self.assertFalse(timer._tts_thread.is_alive())
        self.assertEqual(spoken, ['first', 'new'])

    def test_leader_announced_only_on_their_lap(self):
        def lane(times):
            return SimpleNamespace(laps=[('', t) for t in times], lapSplit=MagicMock(), spt=MagicMock(), l=MagicMock())
        timer.colGreen, timer.colRed = 'green', 'red'
        timer.time_trial_mode = False
        cases = [([2], [], 1, 'Lane 1 in the lead'),
                 ([2, 3], [4], 2, None),
                 ([2], [3], 2, None),
                 ([3], [2], 2, 'Lane 2 in the lead'),
                 ([2], [3], 1, 'Lane 1 in the lead'),
                 ([2], [2], 2, None),
                 ([], [2], 2, 'Lane 2 in the lead')]
        for first, second, completed, expected in cases:
            with self.subTest(first=first, second=second, completed=completed):
                timer.sw, timer.sw2 = lane(first), lane(second)
                with patch.object(timer, 'speak') as speak:
                    timer.splitTimes(timer.sw if completed == 1 else timer.sw2)
                    if expected:
                        speak.assert_called_once_with(expected)
                    else:
                        speak.assert_not_called()
        timer.time_trial_mode = True
        with patch.object(timer, 'speak') as speak:
            timer.splitTimes(timer.sw2)
            speak.assert_not_called()

    def test_time_trial_lap_announces_time(self):
        timer.time_trial_mode = True
        timer.sw = MagicMock()
        timer.sw2 = MagicMock()
        lap = SimpleNamespace(_running=True, _start=0, lapmod2=0, laps=[],
                              _setLapTime=lambda t: str(t), m=MagicMock(),
                              lapstr=MagicMock(), _bestLap=MagicMock())
        with patch.object(timer, 'splitTimes'), patch.object(timer, 'speak') as speak:
            timer.StopWatch.Lap(lap, event_time=3.452)
        speak.assert_called_once_with('3 point 4 5 2')

    def test_race_winner_announced_once_and_reset(self):
        def lane():
            return SimpleNamespace(_running=True, _start=0, lapmod2=0, laps=[],
                                   _setLapTime=lambda t: str(t), m=MagicMock(),
                                   lapstr=MagicMock(), lapSplit=MagicMock(),
                                   spt=MagicMock(), l=MagicMock(), _bestLap=MagicMock(),
                                   Stop=MagicMock(), Reset=MagicMock())
        timer.time_trial_mode = False
        timer.colGreen, timer.colRed = 'green', 'red'
        timer.LapRace = MagicMock()
        timer.LapRace.get.return_value = '1'
        for first_lane in (1, 2):
            with self.subTest(first_lane=first_lane):
                timer.sw, timer.sw2 = lane(), lane()
                timer.race_winner = None
                winner, other = (timer.sw, timer.sw2) if first_lane == 1 else (timer.sw2, timer.sw)
                with patch.object(timer, 'speak') as speak:
                    self.assertTrue(timer.StopWatch.Lap(winner, event_time=2))
                    speak.assert_called_once_with('Lane {} wins'.format(first_lane))
                    speak.reset_mock()
                    timer.StopWatch.Lap(other, event_time=3)
                    speak.assert_not_called()
                    self.assertIs(timer.race_winner, winner)
                timer.ResetRace()
                self.assertIsNone(timer.race_winner)

    def test_rejected_and_disabled_winner_laps(self):
        timer.time_trial_mode = False
        timer.LapRace = MagicMock()
        timer.LapRace.get.return_value = '1'
        timer.sw = SimpleNamespace(_running=True, _start=0, lapmod2=0, laps=[],
                                   _setLapTime=lambda t: str(t), m=MagicMock(),
                                   lapstr=MagicMock(), _bestLap=MagicMock())
        timer.sw2 = MagicMock()
        with patch.object(timer, 'splitTimes'), patch.object(timer, 'speak', wraps=timer.speak) as speak:
            self.assertFalse(timer.StopWatch.Lap(timer.sw, event_time=0.5))
            self.assertIsNone(timer.race_winner)
            timer.tts_enabled = False
            self.assertTrue(timer.StopWatch.Lap(timer.sw, event_time=2))
            self.assertIs(timer.race_winner, timer.sw)
            self.assertTrue(timer.tts_queue.empty())
            speak.assert_called_once_with('Lane 1 wins')

    def test_lap_buttons_follow_time_trial_mode(self):
        timer.time_trial_mode = False
        timer.sw, timer.sw2 = MagicMock(), MagicMock()
        timer.btn_time_trial = MagicMock()
        timer.ToggleTimeTrial()
        timer.sw.lap_button.pack.assert_called_once()
        timer.sw2.lap_button.pack.assert_called_once()
        timer.ToggleTimeTrial()
        timer.sw.lap_button.pack_forget.assert_called_once()
        timer.sw2.lap_button.pack_forget.assert_called_once()


if __name__ == '__main__':
    unittest.main()
