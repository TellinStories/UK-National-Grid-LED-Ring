"""
Grid Ring - TTP223 touch button

Turns touches into three kinds of event:

    TAP   - a touch shorter than 1 second (reported when you let go)
    LONG  - reported as soon as a touch reaches 1 second
    HOLD  - reported as soon as a touch reaches 3 seconds

A touch held for 3 seconds gives LONG at 1 second and then HOLD at 3.

The main loop checks the button 20 times a second. An interrupt also
counts every touch, so a quick tap still registers if the loop was busy
at the time (for example while the grid mode is fetching data).

The TTP223 must be in its default setting (output goes HIGH when touched),
powered from 3.3V, and not touched while it powers up - that's when it
calibrates itself.
"""

import time
from machine import Pin

TAP = "tap"
LONG = "long"
HOLD = "hold"

LONG_MS = 1000
HOLD_MS = 3000


class TouchButton:
    def __init__(self, pin_number):
        self.pin = Pin(pin_number, Pin.IN)
        self._down_since = None    # when the current touch started
        self._fired = None         # LONG or HOLD, once reported for this touch
        self._missed = 0           # touches counted by the interrupt
        self.pin.irq(trigger=Pin.IRQ_RISING, handler=self._irq)

    def _irq(self, _pin):
        self._missed += 1

    def poll(self):
        """Call regularly. Returns TAP, LONG, HOLD or None."""
        now = time.ticks_ms()

        if self.pin.value():                      # being touched now
            if self._down_since is None:
                self._down_since = now
                self._fired = None
                self._missed = 0                  # this touch is being timed normally
                return None
            held = time.ticks_diff(now, self._down_since)
            if held >= HOLD_MS and self._fired != HOLD:
                self._fired = HOLD
                return HOLD
            if held >= LONG_MS and self._fired is None:
                self._fired = LONG
                return LONG
            return None

        if self._down_since is not None:          # just let go
            self._down_since = None
            self._missed = 0
            fired, self._fired = self._fired, None
            return TAP if fired is None else None

        if self._missed > 0:                      # tapped while the loop was busy
            self._missed -= 1
            return TAP

        return None
