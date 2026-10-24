"""
Grid Ring - status light patterns

Patterns shown on the ring:

    Rainbow sweep     - just switched on
    Blue spinner      - connecting to WiFi / waiting for data or the time
    White breathing   - setup mode: join "GridRing-Setup" on a phone
    3 red flashes     - couldn't connect to WiFi (setup mode follows)
    2 green flashes   - settings saved, restarting

Animations run from a timer in the background, so the rest of the code
just starts and stops them.
"""

import math
import time
import micropython
from machine import Timer

import board
import leds

FRAME_MS = 50   # 20 frames per second

BLUE = (0, 70, 255)
WHITE = (150, 150, 150)   # softer than full white, which draws a lot of current
RED = (255, 0, 0)
GREEN = (0, 255, 0)

TAIL = (1.0, 0.4, 0.15, 0.05)   # spinner head and its fading tail

_brightness = 0.3
_pattern = None
_frame = 0
_timer = None


def set_brightness(brightness):
    global _brightness
    _brightness = brightness


# ---------------------------------------------------------------------------
# Patterns - each one draws a single frame
# ---------------------------------------------------------------------------

def _spinner(frame, colour):
    """One bright LED with a fading tail, one lap every 1.2 seconds."""
    head = (frame // 2) % leds.NUM_LEDS
    for i in range(leds.NUM_LEDS):
        distance = (head - i) % leds.NUM_LEDS
        level = TAIL[distance] if distance < len(TAIL) else 0
        leds.np[i] = leds.scaled(colour, level * _brightness)
    leds.np.write()


def _breathe(frame, colour):
    """Whole ring fading smoothly up and down, one breath every 3 seconds."""
    phase = (frame % 60) / 60
    level = 0.05 + 0.95 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
    leds.fill(leds.scaled(colour, level * _brightness))


# ---------------------------------------------------------------------------
# Timer machinery
# ---------------------------------------------------------------------------

def _draw(_):
    global _frame
    if _pattern is None:
        return   # animation was stopped after this frame was queued
    try:
        _pattern(_frame)
    except Exception as e:
        print("Status light error:", e)
    _frame += 1


def _tick(_t):
    # Timer callbacks can run as hardware interrupts, where drawing isn't
    # allowed, so just ask MicroPython to draw at the next safe moment.
    try:
        micropython.schedule(_draw, None)
    except RuntimeError:
        pass     # scheduler busy - skip this frame


def _start(pattern):
    global _pattern, _frame, _timer
    stop()
    _frame = 0
    _pattern = pattern
    _draw(None)            # show the first frame straight away
    _timer = board.new_timer()
    _timer.init(period=FRAME_MS, mode=Timer.PERIODIC, callback=_tick)


def stop():
    """Stops any running animation, leaving the LEDs as they are."""
    global _pattern, _timer
    _pattern = None        # set first, so any frame already queued does nothing
    if _timer is not None:
        _timer.deinit()
        _timer = None


def flash(colour, times, on_ms=300, off_ms=300):
    """Flashes the whole ring. Blocks while it runs, so only used briefly."""
    stop()
    for _ in range(times):
        leds.fill(leds.scaled(colour, _brightness))
        time.sleep_ms(on_ms)
        leds.clear()
        time.sleep_ms(off_ms)


# ---------------------------------------------------------------------------
# Named states, used by the rest of the code
# ---------------------------------------------------------------------------

def connecting():
    _start(lambda frame: _spinner(frame, BLUE))


def setup_mode():
    _start(lambda frame: _breathe(frame, WHITE))


def connection_failed():
    flash(RED, 3)


def settings_saved():
    flash(GREEN, 2)


# Rainbow colours from the original ring clock's start-up display
SPECTRUM = (
    (255, 0, 0), (255, 128, 0), (255, 255, 0), (128, 255, 0),
    (0, 255, 0), (0, 255, 128), (0, 255, 255), (0, 128, 255),
    (0, 0, 255), (128, 0, 255), (255, 0, 255), (255, 0, 128),
)


def startup(top):
    """
    The original ring clock's start-up display: a rainbow sweeps round
    clockwise from 12 o'clock over 1 second, then fades out over 2 seconds.
    `top` is the physical LED at 12 o'clock.
    """
    stop()
    leds.clear()
    n = leds.NUM_LEDS
    for i in range(n):
        leds.np[(top + i) % n] = leds.scaled(SPECTRUM[i], _brightness)
        leds.np.write()
        time.sleep_ms(1000 // n)

    full = [leds.np[i] for i in range(n)]
    steps = 40
    for fade in range(steps, -1, -1):
        for i in range(n):
            r, g, b = full[i]
            leds.np[i] = (r * fade // steps, g * fade // steps, b * fade // steps)
        leds.np.write()
        time.sleep_ms(2000 // steps)
