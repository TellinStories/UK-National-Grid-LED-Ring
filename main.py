"""
Grid Ring - main entry point

A 12-LED ring with three modes, switched by tapping the touch button:

    1. National Grid  - live UK electricity generation mix
    2. Clock          - time from the internet, UK summer time automatic
    3. Pomodoro       - one hour of work and breaks, 5 minutes per LED

Touch button:
    Tap                  - next mode (shown briefly as 1, 2 or 3 white LEDs)
    Hold for 1 second    - start / pause the pomodoro timer
    Hold for 3 seconds   - reset the pomodoro timer

Board button (BOOTSEL on the Pico, BOOT on the XIAO):
    Hold for 3 seconds at any time to open the WiFi / settings setup page.
    (On the XIAO, don't hold it WHILE plugging in - that starts the chip's
    firmware-download mode instead.)

Runs on a Raspberry Pi Pico W / 2 W or a Seeed XIAO ESP32-C3 - board.py
detects which and handles the differences.

To test one mode on its own, remove the others from make_modes() below.
"""

import sys
import time

from config import load_config, save_config
import board
import leds
import status_light
import timesync
import touch
import wifi_setup

import mode_grid
import mode_clock
import mode_pomodoro

LOOP_MS = 50              # check buttons and update the ring 20 times a second
SETUP_HOLD_S = 3          # hold the board button this long for setup mode
MODE_NUMBER_MS = 500      # how long the mode number shows after a tap
MODE_NUMBER_COLOUR = (255, 255, 255)


def make_modes(cfg):
    return [
        mode_grid.GridMode(cfg),
        mode_clock.ClockMode(cfg),
        mode_pomodoro.PomodoroMode(cfg),
    ]


def report(e):
    """Prints an error with its details, without stopping the device."""
    if hasattr(sys, "print_exception"):
        sys.print_exception(e)
    else:
        print("Error:", e)


def show_mode_number(number, cfg):
    """Lights 1, 2 or 3 white LEDs clockwise from 12 o'clock."""
    top = cfg.get("start_led", 6)
    colour = leds.scaled(MODE_NUMBER_COLOUR, cfg.get("brightness", 0.3))
    for i in range(leds.NUM_LEDS):
        leds.np[i] = (0, 0, 0)
    for i in range(number):
        leds.np[(top + i) % leds.NUM_LEDS] = colour
    leds.np.write()
    time.sleep_ms(MODE_NUMBER_MS)


def saved_mode_index(cfg, modes):
    for i, mode in enumerate(modes):
        if mode.name == cfg.get("mode"):
            return i
    return 0


def run_modes(cfg):
    """The main loop. Only returns if the board button is held for setup."""
    modes = make_modes(cfg)
    index = saved_mode_index(cfg, modes)
    button = touch.TouchButton(board.TOUCH_PIN)
    board_button_since = None

    status_light.stop()
    print("Starting in mode:", modes[index].name)
    modes[index].start()

    while True:
        now = time.ticks_ms()

        # Touch button: tap = next mode, long press / hold = mode's own action
        event = button.poll()
        try:
            if event == touch.TAP:
                modes[index].stop()
                index = (index + 1) % len(modes)
                print("Mode:", modes[index].name)
                show_mode_number(index + 1, cfg)
                modes[index].start()
                cfg["mode"] = modes[index].name
                save_config(cfg)        # remembered after a power cut
            elif event == touch.LONG:
                modes[index].on_long_press()
            elif event == touch.HOLD:
                modes[index].on_hold()
        except Exception as e:
            report(e)

        # Board button held for 3 seconds: open the setup page
        if board.button_pressed():
            if board_button_since is None:
                board_button_since = now
            elif time.ticks_diff(now, board_button_since) >= SETUP_HOLD_S * 1000:
                print(board.BUTTON_NAME, "button held - entering setup mode")
                modes[index].stop()
                return
        else:
            board_button_since = None

        # Housekeeping, then let the current mode update the ring
        try:
            wifi_setup.keep_connected(cfg)
            timesync.maybe_sync()
            for mode in modes:
                mode.background()
            modes[index].update()
        except Exception as e:
            report(e)

        time.sleep_ms(LOOP_MS)


def main():
    print("Grid Ring starting on", board.BOARD_NAME)
    cfg = load_config()
    status_light.set_brightness(cfg.get("brightness", 0.3))

    # Board button held just after power-up, or nothing saved yet
    if board.button_held(SETUP_HOLD_S) or not cfg.get("ssid"):
        wifi_setup.run_setup_portal(cfg)   # reboots once settings are saved
        return

    status_light.startup(cfg.get("start_led", 6))   # rainbow hello
    status_light.connecting()
    if not wifi_setup.connect_with_saved(cfg):
        status_light.connection_failed()
        wifi_setup.run_setup_portal(cfg)
        return

    timesync.maybe_sync(force=True)
    run_modes(cfg)                      # returns only when setup is requested
    wifi_setup.run_setup_portal(cfg)


if __name__ == "__main__":
    main()
