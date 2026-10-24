"""
Grid Ring - configuration persistence

Reads/writes a small JSON file on the board's flash so settings survive
power cycles and don't need to be edited in Thonny by the end user.
"""

import ujson

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "ssid": "",
    "password": "",
    "brightness": 0.3,                 # 0.05-1.0
    "start_led": 6,                    # 0-11, the physical LED at 12 o'clock
    "bucket_order": [                  # grid colours, clockwise from 12 o'clock
        "renewable", "nuclear", "other_misc", "biomass", "fossil"
    ],
    "mode": "grid",                    # mode showing when last switched off
}


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = ujson.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        return merged
    except (OSError, ValueError):
        # No file yet, or it's corrupt - fall back to defaults
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        ujson.dump(cfg, f)
