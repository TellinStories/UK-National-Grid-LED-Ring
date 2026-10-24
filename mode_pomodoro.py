"""
Grid Ring - pomodoro timer mode

The ring shows one hour - two pomodoro cycles - with each LED worth
5 minutes, clockwise from 12 o'clock:

    5 red (25 minutes' work), 1 green (5-minute break),
    5 red (25 minutes' work), 1 green (5-minute break)

While the timer runs, the current LED fades slowly to black over its
5 minutes, then the next one starts fading, and so on round the ring.

Touch controls in this mode:
    Tap                  - switch to the next mode (the timer keeps running)
    Hold for 1 second    - start / pause
    Hold for 3 seconds   - reset to a full ring

What you'll see:
    Whole ring dips briefly           - your 1-second hold has started or
                                        paused the timer: let go now
    Whole ring fades out and back in  - your 3-second hold has reset it
    Current LED gently breathing      - ready to start, or paused
    New LED pulsing 3 times           - work has just turned to break, or back
    Whole ring pulsing 3 times        - the hour is up; it then resets

The pulse speeds are set by the *_PULSE_MS values below - larger is slower.
"""

import math
import time
import leds

SEGMENT_MS = 5 * 60 * 1000              # each LED is 5 minutes
SEGMENTS = 12
TOTAL_MS = SEGMENTS * SEGMENT_MS        # one hour
BREAK_SEGMENTS = (5, 11)                # the 6th and 12th LEDs are breaks

WORK_COLOUR = (255, 0, 0)               # red
BREAK_COLOUR = (0, 255, 0)              # green

PAUSED_PULSE_MS = 3000                  # one slow breath every 3 s when ready / paused
PAUSED_MIN_LEVEL = 0.25                 # keep it visible near the end of an LED
ALERT_PULSES = 3                        # pulses at a work <-> break change
ALERT_PULSE_MS = 2000
FINISH_PULSES = 3                       # whole-ring pulses when the hour is up
FINISH_PULSE_MS = 2000
FINISH_MS = int((FINISH_PULSES + 0.5) * FINISH_PULSE_MS)   # ends faded fully back in

# Acknowledgements, so you know when to let go of the touch pad
START_PAUSE_DIP_MS = 600                # quick dip of the whole ring...
START_PAUSE_DIP_DEPTH = 0.75            # ...down to a quarter brightness
RESET_FADE_MS = 1200                    # slower fade right out and back in


def _is_break(segment):
    return segment in BREAK_SEGMENTS


def _dim(colour, factor):
    """Scales a colour, but keeps any lit channel at 1 or more while factor > 0,
    so a nearly-finished LED stays faintly visible until its time is really up."""
    if factor <= 0:
        return (0, 0, 0)
    return tuple(max(1, int(c * factor)) if c else 0 for c in colour)


def _pulse(ms_since, period_ms, start_lit=True):
    """
    Smooth fade out and back in (or in and out, if start_lit is False),
    from 1 down to 0 and back over each period. Squared because our eyes see
    brightness non-linearly - without it the LED seems to hang at full and
    then drop away suddenly.
    """
    wave = 0.5 + 0.5 * math.cos(2 * math.pi * ms_since / period_ms)
    if not start_lit:
        wave = 1 - wave
    return wave * wave


def _dip(ms_since, length_ms, depth):
    """Brightness multiplier that eases down by `depth` and back up to 1."""
    return 1 - depth * math.sin(math.pi * ms_since / length_ms)


def _mmss(ms):
    s = ms // 1000
    return "{:02d}:{:02d}".format(s // 60, s % 60)


class PomodoroMode:
    name = "pomodoro"

    def __init__(self, cfg):
        self.top = cfg.get("start_led", 6)
        self.brightness = cfg.get("brightness", 0.3)
        self.reset()

    def reset(self):
        self.running = False
        self.done_ms = 0            # time completed before the current run
        self.run_start = None       # when the current run started (ticks)
        self.finished_at = None     # when the hour ran out (ticks)
        self.segment = 0            # segment the display was last drawn for
        self.alert_start = None     # start of a work <-> break pulse (ticks)
        self.pulse_from = time.ticks_ms()   # breathing starts from fully lit
        self.ack_start = None       # start of a touch acknowledgement (ticks)
        self.ack_ms = 0             # its length
        self.ack_depth = 0          # how far it dims the ring
        self.shown = None           # last frame written to the ring

    def _acknowledge(self, length_ms, depth):
        self.ack_start = time.ticks_ms()
        self.ack_ms = length_ms
        self.ack_depth = depth

    def elapsed(self, now):
        if self.running:
            return self.done_ms + time.ticks_diff(now, self.run_start)
        return self.done_ms

    # --- touch actions -----------------------------------------------------

    def on_long_press(self):
        now = time.ticks_ms()
        if self.finished_at is not None:
            self.reset()
        if self.running:
            self.done_ms = self.elapsed(now)
            self.running = False
            self.pulse_from = now
            print("Pomodoro paused at", _mmss(self.done_ms))
        else:
            self.run_start = now
            self.running = True
            print("Pomodoro started" if self.done_ms == 0
                  else "Pomodoro resumed at " + _mmss(self.done_ms))
        self.alert_start = None
        self.shown = None
        self._acknowledge(START_PAUSE_DIP_MS, START_PAUSE_DIP_DEPTH)

    def on_hold(self):
        self.reset()
        self._acknowledge(RESET_FADE_MS, 1)
        print("Pomodoro reset")

    # --- called by the main loop ---------------------------------------------

    def start(self):
        self.shown = None           # force a redraw
        if not self.running:
            self.pulse_from = time.ticks_ms()   # breathe from fully lit

    def stop(self):
        pass                        # the timer carries on in the background

    def background(self):
        """Runs even when another mode is showing, to stop at the end of the hour."""
        if self.running and self.elapsed(time.ticks_ms()) >= TOTAL_MS:
            self.done_ms = TOTAL_MS
            self.running = False
            self.finished_at = time.ticks_ms()
            print("Pomodoro hour complete")

    def update(self):
        now = time.ticks_ms()
        self.background()

        if self.finished_at is not None:
            since = time.ticks_diff(now, self.finished_at)
            if 0 <= since < FINISH_MS:
                level = _pulse(since, FINISH_PULSE_MS, start_lit=False)
                self._show(self._full_frame(level))
                return
            self.reset()            # pulsing done - back to a full ring

        elapsed = self.elapsed(now)
        segment = min(elapsed // SEGMENT_MS, SEGMENTS - 1)

        if segment != self.segment:
            if self.running and _is_break(segment) != _is_break(self.segment):
                self.alert_start = now
                print("Pomodoro: break time" if _is_break(segment) else "Pomodoro: back to work")
            self.segment = segment

        self._show(self._frame(now, elapsed, segment))

    # --- drawing ---------------------------------------------------------------

    def _full_frame(self, level=1):
        return [_dim(BREAK_COLOUR if _is_break(i) else WORK_COLOUR, level * self.brightness)
                for i in range(SEGMENTS)]

    def _ack_level(self, now):
        """1 normally; less while acknowledging a long press or reset."""
        if self.ack_start is None:
            return 1
        since = time.ticks_diff(now, self.ack_start)
        if 0 <= since < self.ack_ms:
            return _dip(since, self.ack_ms, self.ack_depth)
        self.ack_start = None
        return 1

    def _frame(self, now, elapsed, segment):
        ack = self._ack_level(now)
        alert_ms = None
        if self.alert_start is not None:
            alert_ms = time.ticks_diff(now, self.alert_start)
            if not 0 <= alert_ms < ALERT_PULSES * ALERT_PULSE_MS:
                alert_ms = None
                self.alert_start = None

        frame = []
        for i in range(SEGMENTS):
            colour = BREAK_COLOUR if _is_break(i) else WORK_COLOUR
            if i < segment:
                level = 0                       # used up
            elif i > segment:
                level = 1                       # still to come
            else:
                left = 1 - (elapsed - segment * SEGMENT_MS) / SEGMENT_MS
                # Squared so the 5-minute fade looks steady to the eye
                level = left * left
                if not self.running:
                    level = max(level, PAUSED_MIN_LEVEL)
                    level *= _pulse(time.ticks_diff(now, self.pulse_from), PAUSED_PULSE_MS)
                elif alert_ms is not None:
                    level *= _pulse(alert_ms, ALERT_PULSE_MS)
            frame.append(_dim(colour, level * ack * self.brightness))
        return frame

    def _show(self, frame):
        if frame == self.shown:
            return                  # only write to the LEDs when something changes
        self.shown = frame
        for i in range(SEGMENTS):
            leds.np[(self.top + i) % leds.NUM_LEDS] = frame[i]
        leds.np.write()
