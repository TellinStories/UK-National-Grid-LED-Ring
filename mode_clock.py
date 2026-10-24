"""
Grid Ring - clock mode

Based on RGB LED Ring Clock, Copyright (c) 2026 John Dovey, released under
the MIT License. Adapted to take the time from the internet (see
timesync.py), so it needs no RTC module or daylight-saving switch.

The display, as in the original:
  - Hour hand: blue, on the LED for the current hour.
  - Minute hand: the LED for the current 5 minutes (12 o'clock = 0-4
    minutes past). Its colour steps red, orange, yellow, yellow-green,
    green through each 5 minutes.
  - When both hands share an LED, it shows shades of purple instead.

While waiting for the time from the internet it shows the blue spinner.
"""

import leds
import status_light
import timesync

# The original colours were (R, G, B) at a maximum of 60. These are the same
# colours at full scale; the brightness setting scales them down.
HOUR_COLOUR = (0, 0, 255)

# Minute hand colour for 0, 1, 2, 3 and 4 minutes into each 5 minutes
MINUTE_COLOURS = (
    (255, 0, 0),      # red
    (255, 128, 0),    # orange
    (255, 255, 0),    # yellow
    (128, 255, 0),    # yellow-green
    (0, 255, 0),      # green
)

# When the hour and minute hands share an LED
SHARED_COLOURS = (
    (128, 0, 255),
    (191, 0, 191),
    (255, 0, 255),
    (255, 0, 191),
    (255, 0, 128),
)


class ClockMode:
    name = "clock"

    def __init__(self, cfg):
        self.top = cfg.get("start_led", 6)
        self.brightness = cfg.get("brightness", 0.3)
        self.shown = None        # (hour, minute) currently on the ring
        self.waiting = False     # showing the spinner while waiting for the time

    def _pixel(self, position):
        """Clock position 0-11 (0 = 12 o'clock) to physical LED."""
        return (position + self.top) % leds.NUM_LEDS

    def start(self):
        self.shown = None        # force a redraw
        self.waiting = False

    def stop(self):
        if self.waiting:
            status_light.stop()
            self.waiting = False

    def update(self):
        if not timesync.time_known():
            if not self.waiting:
                status_light.connecting()
                self.waiting = True
            return
        if self.waiting:
            status_light.stop()
            self.waiting = False

        t = timesync.uk_time()
        hour, minute = t[3], t[4]
        if (hour, minute) == self.shown:
            return               # nothing has changed since the last draw
        self.shown = (hour, minute)
        self.draw(hour, minute)
        print("Clock: {:02d}:{:02d}".format(hour, minute))

    def draw(self, hour, minute):
        hour_hand = hour % 12            # 0 = 12 o'clock
        minute_hand = minute // 5        # minutes 5-9 -> 1, 10-14 -> 2, ...
        step = minute % 5                # how far through those 5 minutes

        for i in range(leds.NUM_LEDS):
            leds.np[i] = (0, 0, 0)
        if hour_hand == minute_hand:
            leds.np[self._pixel(minute_hand)] = leds.scaled(SHARED_COLOURS[step], self.brightness)
        else:
            leds.np[self._pixel(hour_hand)] = leds.scaled(HOUR_COLOUR, self.brightness)
            leds.np[self._pixel(minute_hand)] = leds.scaled(MINUTE_COLOURS[step], self.brightness)
        leds.np.write()

    def background(self):
        pass

    def on_long_press(self):
        pass

    def on_hold(self):
        pass
