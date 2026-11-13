# Plan: lap history, daily bests and drivers

Status: idea, not started.

## Goal

Collect every lap so that the best lap per lane per day, and optionally per driver per day, can be seen afterwards. Time trial and race laps are kept apart.

## Constraints

- Lap registering is the core of the program and must not be affected. Saving, checking and showing history must never delay or block a lap.
- Driver information is optional. A race or time trial must start without it, and nothing may prompt for it during racing.
- Not every lap trigger is a real lap. Most bad laps are **too short**: the car derails, a time trial lap is restarted, or the car is put back on the track past the sensor.

## Storage

SQLite file next to the app (`sqlite3` is in the Python standard library, no server needed).

### `laps`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `recorded_at` | UTC timestamp of the crossing |
| `day` | Local date, used for daily results |
| `lane` | 1 or 2 |
| `mode` | `time_trial` or `race` |
| `session_id` | New id at each Reset, Start or Lights |
| `lap_no` | Lap number within the session |
| `lap_ms` | Lap time in milliseconds |
| `status` | `valid`, `suspect` or `rejected` |
| `reason` | Why a lap is suspect or rejected, e.g. `voided`, `too_fast`, `manual`, `standing_start` |
| `driver_id` | Nullable. Empty means no driver was chosen |

### `drivers`

| Column | Notes |
|---|---|
| `id` | Primary key |
| `name` | Display name |

### Writing

Laps are written from a background worker thread fed by a queue, the same pattern as the TTS worker. `Lap()` only puts the finished lap on the queue. A slow SD card or a database error must never reach the lap registering code; errors are printed and the lap still shows on screen.

## Which laps count

Only valid laps count toward bests. Since a too-long lap can never become a best, the checks only need to catch too-short laps.

1. **Hard minimum.** Raise `MIN_LAP_TIME_SEC` to a realistic value for the track (well below the real record). Anything shorter is not registered at all.
2. **Suspect check.** Reference = best valid lap for the same lane and mode in the last 30 days. If there is no history yet, use a configurable `MIN_VALID_LAP_SEC`. A lap more than 15% faster than the reference is saved as `suspect` and does not count until confirmed. It still counts as a lap in the running session.
3. **Void button.** In time trial mode each lane gets a **Void** button next to **Lap**. Pressing it after a derailment marks the lap in progress as `rejected` (`voided`) when it ends at the next crossing. The lap is still shown, struck through.
4. **Manual review.** Tapping a lap in the lane's list toggles it between valid and rejected, or confirms a suspect lap. Also available in the web view.
5. **Race standing start.** The first lap of a race includes the start reaction. It is saved as valid with reason `standing_start` and shown separately from flying race laps in race bests.

Thresholds (`MIN_LAP_TIME_SEC`, `MIN_VALID_LAP_SEC`, 15%, 30 days) are constants at the top of `timer_lapper.py`, tuned after real use.

## Drivers

- Each lane shows a driver label near its lap counter, `—` by default.
- Tapping it opens a short list of names with `—` at the top. One tap, no typing on the race screen.
- The lane remembers the last driver across Reset and new sessions until it is changed.
- The driver is saved on each lap when it is recorded, so changing drivers mid-session affects only the following laps.
- Start, Lights and Time Trial never check for a driver.
- New drivers are added outside racing, in the web view.
- Laps can be assigned a driver afterwards in the web view, per session or per lap.

## Results

All results are split by mode. Only `valid` laps count.

- **Per lane per day:** all valid laps, with or without a driver.
- **Per driver per day:** valid laps with a driver, across both lanes, lane shown as detail.
- Suspect laps show as "awaiting review" next to the bests.

Example daily view:

| Day | Lane | Best time trial | Best race lap | Laps (valid / rejected) |
|---|---|---|---|---|
| 2026-11-13 | 1 | 21.384 | 22.010 | 34 / 3 |

### Where results are shown

- **Timer screen:** a "Today's best" line per lane, next to the current session's Best.
- **Web view:** a small web page served from the Pi (e.g. Flask), opened from a phone. History by day, lane and driver; lap review; managing drivers; assigning drivers afterwards.

## Build order

1. Save laps to SQLite through a worker queue, with `mode`, `status` and an empty `driver_id`.
2. Void button in time trial mode.
3. Suspect check and raised `MIN_LAP_TIME_SEC`.
4. "Today's best" line on the timer screen, and manual review in the lap list.
5. Driver label and picker on each lane.
6. Web view: history, review, drivers, assigning drivers afterwards.

Each step is useful on its own. Adding `driver_id` in step 1 means laps recorded before drivers exist can be given a driver later without changing the database.

## Open questions

- Realistic values for `MIN_LAP_TIME_SEC`, `MIN_VALID_LAP_SEC` and the suspect percentage on this track.
- How long to keep history, or keep everything (a lap row is tiny, so years fit easily)?
- Should the web view be reachable only on the home network, and does it need any login?
