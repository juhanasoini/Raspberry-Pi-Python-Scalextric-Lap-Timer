import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from test_tts import timer


class RaceTimingTests(unittest.TestCase):
    def setUp(self):
        timer.countdown_job = None
        timer.countdown_widgets = []
        timer.time_trial_mode = False
        timer.race_laps = 2
        timer.colFg1, timer.colGreen, timer.colRed = 'grey', 'green', 'red'

    def test_sensor_uses_capture_timestamp_and_rejects_stale_events(self):
        lane = SimpleNamespace(_event_cutoff=10, _last_trigger_time=0, _running=True,
                               laps=[], Lap=MagicMock(), Finish=MagicMock())
        self.assertFalse(timer.StopWatch.gpioTrigger(lane, 9))
        self.assertTrue(timer.StopWatch.gpioTrigger(lane, 12))
        lane.Lap.assert_called_once_with(event_time=12)
        lane.laps.append(('2', 2))
        self.assertTrue(timer.StopWatch.gpioTrigger(lane, 14))
        lane.Finish.assert_called_once_with(event_time=14)

    def test_time_trial_starts_at_crossing_and_rejects_countdown_crossing(self):
        timer.time_trial_mode = True
        lane = SimpleNamespace(_event_cutoff=10, _last_trigger_time=0, _running=False,
                               Start=MagicMock(), Lap=MagicMock())
        timer.countdown_job = 'pending'
        self.assertFalse(timer.StopWatch.gpioTrigger(lane, 11))
        timer.countdown_job = None
        self.assertTrue(timer.StopWatch.gpioTrigger(lane, 12))
        lane.Start.assert_called_once_with(silent=True, event_time=12)

    def test_invalid_laps_and_captured_count(self):
        timer.LapRace = MagicMock()
        with patch.object(timer.messagebox, 'showerror') as error:
            for value in ('', 'abc', '0', '-2', '1.5'):
                timer.LapRace.get.return_value = value
                self.assertFalse(timer.validRaceLaps())
            self.assertEqual(error.call_count, 5)
        timer.LapRace.get.return_value = '4'
        self.assertTrue(timer.validRaceLaps())
        timer.LapRace.get.return_value = '7'
        self.assertEqual(timer.race_laps, 4)

    def test_split_uses_latest_common_lap_and_ties_are_neutral(self):
        def lane(values):
            return SimpleNamespace(laps=[('', value) for value in values],
                                   lapSplit=MagicMock(), spt=MagicMock(), l=MagicMock())
        timer.sw, timer.sw2 = lane([2, 3]), lane([4])
        with patch.object(timer, 'speak'):
            timer.splitTimes(timer.sw)
        timer.sw.lapSplit.set.assert_called_with('Lap 1 gap: -2.000')
        timer.sw2.lapSplit.set.assert_called_with('Lap 1 gap: +2.000')
        timer.sw, timer.sw2 = lane([2]), lane([2])
        with patch.object(timer, 'speak') as speak:
            timer.splitTimes(timer.sw)
        timer.sw.l.config.assert_called_with(fg='grey')
        timer.sw2.l.config.assert_called_with(fg='grey')
        speak.assert_not_called()

    def test_countdown_schedules_steps_and_can_be_cancelled(self):
        timer.root = SimpleNamespace(tk=MagicMock())
        timer.root.tk.after.side_effect = ['first', 'second', 'third', 'green', 'cleanup']
        timer.LapRace = MagicMock()
        timer.LapRace.get.return_value = '3'
        timer.sw, timer.sw2 = MagicMock(), MagicMock()
        timer.colBg1 = 'black'
        with patch.object(timer, 'PhotoImage'), patch.object(timer, 'Canvas'), patch.object(timer, 'Label'):
            timer.RaceLights()
            self.assertEqual(timer.countdown_job, 'first')
            for _ in range(4):
                args = timer.root.tk.after.call_args.args
                args[1](*args[2:])
            timer.sw.Start.assert_called_once()
            timer.sw2.Start.assert_called_once()
            self.assertEqual(timer.countdown_job, 'cleanup')
            timer.cancelCountdown()
            timer.root.tk.after_cancel.assert_called_with('cleanup')
            self.assertEqual(timer.countdown_widgets, [])


if __name__ == '__main__':
    unittest.main()
