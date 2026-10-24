"""
Grid Ring - board-specific settings

Everything that differs between the supported boards lives here, and the
board is detected automatically - the same files run on both:

    Raspberry Pi Pico 2 W  (also Pico W)
    Seeed XIAO ESP32-C3

If you wire the LED ring or touch button to different pins, change
LED_PIN or TOUCH_PIN below.
"""

import sys
import time
from machine import Pin, Timer

IS_PICO = sys.platform == "rp2"

if IS_PICO:
    BOARD_NAME = "Raspberry Pi Pico W / 2 W"
    LED_PIN = 0          # GP0
    TOUCH_PIN = 1        # GP1 - any free GP pin will do
    BUTTON_NAME = "BOOTSEL"

    def button_pressed():
        import rp2
        return rp2.bootsel_button() == 1

    def new_timer():
        return Timer(-1)          # software timer

else:
    BOARD_NAME = "Seeed XIAO ESP32-C3"
    LED_PIN = 10         # GPIO10, the pin labelled D10
    TOUCH_PIN = 20       # GPIO20, the pin labelled D7
    BUTTON_NAME = "BOOT"

    # The XIAO's BOOT button is on GPIO9 and reads 0 when pressed.
    # Holding it while powering up starts the chip's firmware-download mode
    # instead of MicroPython, so it's only used as a button once running.
    _boot_button = Pin(9, Pin.IN, Pin.PULL_UP)

    def button_pressed():
        return _boot_button.value() == 0

    def new_timer():
        return Timer(0)           # hardware timer 0


def button_held(hold_s):
    """
    True if the button is pressed now and stays pressed for hold_s seconds.
    Returns straight away if it isn't pressed, so it's cheap to call often.
    """
    if not button_pressed():
        return False
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < hold_s * 1000:
        if not button_pressed():
            return False          # released early - not a deliberate hold
        time.sleep_ms(50)
    return True


def configure_setup_network(ap, ssid):
    """
    Starts the setup access point as an OPEN network (no password).
    The two boards need this done differently:
      - Pico: defaults to WPA2 with a built-in password, so security=0 is
        needed, and settings must be applied BEFORE the access point starts.
      - ESP32: uses authmode instead, applied after the access point starts.
    """
    import network
    if IS_PICO:
        ap.config(essid=ssid, security=0)
        ap.active(True)
    else:
        ap.active(True)
        ap.config(essid=ssid, authmode=network.AUTH_OPEN)
