"""
Grid Ring - LED ring hardware

Sets up the NeoPixel ring on the pin given in board.py. Both the data
display and the status patterns use this.
"""

from machine import Pin
import neopixel

import board

NUM_LEDS = 12

np = neopixel.NeoPixel(Pin(board.LED_PIN), NUM_LEDS)


def scaled(colour, brightness):
    """Scales an (R, G, B) colour by a 0.0-1.0 brightness."""
    return tuple(int(c * brightness) for c in colour)


def fill(colour):
    for i in range(NUM_LEDS):
        np[i] = colour
    np.write()


def clear():
    fill((0, 0, 0))
