"""
Grid Ring - internet time and UK summer time

Sets the board's clock from an internet time server (NTP) once WiFi is
connected, then re-syncs every 6 hours because the board's own clock
drifts by a few seconds a day. The board keeps time between syncs, so the
clock carries on if WiFi drops - but it needs WiFi once after power-up.

Internet time is UTC (the same as GMT). UK summer time (BST, one hour
ahead) is worked out here, so no daylight-saving switch is needed:
it runs from 01:00 UTC on the last Sunday in March to 01:00 UTC on the
last Sunday in October.
"""

import time
import network
import ntptime

RESYNC_S = 6 * 60 * 60     # re-sync every 6 hours once the time is known
RETRY_S = 60               # until then, try every minute

_known = False
_last_attempt = None


def _weekday(year, month, day):
    """Day of the week, 0 = Sunday ... 6 = Saturday (Sakamoto's method)."""
    offsets = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if month < 3:
        year -= 1
    return (year + year // 4 - year // 100 + year // 400
            + offsets[month - 1] + day) % 7


def _last_sunday(year, month):
    """Date of the last Sunday in a 31-day month (March or October)."""
    return 31 - _weekday(year, month, 31)


def is_uk_summer_time(year, month, day, hour):
    """True if the given UTC date and hour falls in UK summer time (BST)."""
    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True
    change_day = _last_sunday(year, month)
    if month == 3:
        return (day, hour) >= (change_day, 1)
    return (day, hour) < (change_day, 1)      # October


def time_known():
    return _known


def maybe_sync(force=False):
    """Call from the main loop - syncs with the internet when it's due."""
    global _known, _last_attempt
    now = time.ticks_ms()
    if not force and _last_attempt is not None:
        age = time.ticks_diff(now, _last_attempt)
        wait = RESYNC_S if _known else RETRY_S
        if 0 <= age < wait * 1000:
            return
    if not network.WLAN(network.STA_IF).isconnected():
        return
    _last_attempt = now
    try:
        ntptime.settime()       # sets the board's clock to UTC
    except Exception as e:
        print("Couldn't get the time from the internet:", e)
        return
    _known = True
    t = uk_time()
    print("Time set from the internet: {:02d}:{:02d}:{:02d} UK time".format(t[3], t[4], t[5]))


def uk_time():
    """Current UK time as a tuple: (year, month, day, hour, minute, second, ...)."""
    now = time.time()
    t = time.localtime(now)       # the board's clock is on UTC
    if is_uk_summer_time(t[0], t[1], t[2], t[3]):
        t = time.localtime(now + 3600)
    return t
