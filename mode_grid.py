"""
Grid Ring - National Grid mode

Shows the live GB electricity generation mix as coloured arcs around the
ring, clockwise from 12 o'clock in the order set on the setup page.

New figures are fetched every 5 minutes while this mode is showing.
Switching away and back shows the last figures straight away, and
refreshes them if they're more than 5 minutes old.

Data source: Carbon Intensity API (api.carbonintensity.org.uk) - free and
needs no key, so please don't poll it more often than every few minutes.
"""

import gc
import time
import urequests

import leds
import status_light

POLL_INTERVAL_S = 5 * 60    # 5 minutes between updates
RETRY_S = 30                # retry sooner if there's nothing to show yet

API_URL = "https://api.carbonintensity.org.uk/generation"

# Colour per bucket (R, G, B), 0-255 before brightness scaling
COLOURS = {
    "renewable": (0, 160, 60),    # green
    "nuclear": (0, 90, 200),      # blue
    "other_misc": (110, 40, 170), # purple - storage + interconnectors
    "biomass": (200, 90, 0),      # orange
    "fossil": (200, 0, 0),        # red
}

# Which API fuel keys feed into which colour bucket.
# The API's own "other" fuel key is its catch-all for storage (pumped
# hydro, battery) - it lands in the same bucket as imports/interconnectors.
FUEL_TO_BUCKET = {
    "solar": "renewable",
    "wind": "renewable",
    "hydro": "renewable",
    "nuclear": "nuclear",
    "imports": "other_misc",
    "other": "other_misc",
    "biomass": "biomass",
    "coal": "fossil",
    "gas": "fossil",
}


FETCH_TIMEOUT_S = 10        # give up rather than freeze if the internet is down


def _get(url, headers):
    try:
        return urequests.get(url, headers=headers, timeout=FETCH_TIMEOUT_S)
    except TypeError:       # older urequests versions have no timeout option
        return urequests.get(url, headers=headers)


def fetch_generation_mix():
    """Returns a dict like {'coal': 0.0, 'gas': 15.2, 'wind': 49.1, ...}"""
    response = _get(API_URL, {"Accept": "application/json"})
    try:
        data = response.json()
    finally:
        response.close()

    mix = {}
    for entry in data["data"]["generationmix"]:
        mix[entry["fuel"]] = entry["perc"]
    return mix


def group_into_buckets(mix, bucket_order):
    totals = {b: 0.0 for b in bucket_order}
    for fuel, pct in mix.items():
        bucket = FUEL_TO_BUCKET.get(fuel)
        if bucket in totals:
            totals[bucket] += pct
    return totals


def allocate_leds(bucket_totals, bucket_order, num_leds=leds.NUM_LEDS):
    """
    Converts bucket percentages into whole numbers of LEDs that sum to
    exactly num_leds, using the largest-remainder method. Shares are worked
    out from the actual total rather than assuming exactly 100%, so the
    ring is always fully lit even if the API's figures don't quite add up.
    """
    grand_total = sum(bucket_totals[b] for b in bucket_order)
    if grand_total <= 0:
        raise ValueError("No generation data in response")

    raw = {b: bucket_totals[b] / grand_total * num_leds for b in bucket_order}
    floors = {b: int(raw[b]) for b in bucket_order}
    remainder = num_leds - sum(floors.values())

    remainders_sorted = sorted(
        bucket_order, key=lambda b: raw[b] - floors[b], reverse=True
    )
    for b in remainders_sorted[:remainder]:
        floors[b] += 1

    return floors


def show_mix(led_counts, bucket_order, top, brightness):
    index = top
    for bucket in bucket_order:
        colour = leds.scaled(COLOURS[bucket], brightness)
        for _ in range(led_counts[bucket]):
            leds.np[index % leds.NUM_LEDS] = colour
            index += 1
    leds.np.write()


class GridMode:
    name = "grid"

    def __init__(self, cfg):
        self.bucket_order = cfg.get("bucket_order")
        self.top = cfg.get("start_led", 6)
        self.brightness = cfg.get("brightness", 0.3)
        self.counts = None          # last good reading, as LEDs per bucket
        self.last_attempt = None    # when we last tried to fetch

    def start(self):
        if self.counts:
            show_mix(self.counts, self.bucket_order, self.top, self.brightness)
        else:
            status_light.connecting()   # spinner until the first reading

    def stop(self):
        status_light.stop()

    def _due(self):
        if self.last_attempt is None:
            return True
        age = time.ticks_diff(time.ticks_ms(), self.last_attempt)
        wait = POLL_INTERVAL_S if self.counts else RETRY_S
        # age < 0 only happens if the mode was away for days and the
        # millisecond counter wrapped round - just fetch again
        return age < 0 or age >= wait * 1000

    def update(self):
        if not self._due():
            return
        self.last_attempt = time.ticks_ms()
        try:
            gc.collect()    # free memory before the secure connection
            mix = fetch_generation_mix()
            totals = group_into_buckets(mix, self.bucket_order)
            counts = allocate_leds(totals, self.bucket_order)
        except Exception as e:
            # Keep showing the last good reading rather than blanking the
            # ring - nicer behaviour for something sitting on a shelf.
            print("Grid update failed, keeping last reading:", e)
            return
        status_light.stop()     # end the spinner, if it's still running
        self.counts = counts
        show_mix(counts, self.bucket_order, self.top, self.brightness)
        print("Grid updated:", totals, "->", counts)

    def background(self):
        pass

    def on_long_press(self):
        pass

    def on_hold(self):
        pass
