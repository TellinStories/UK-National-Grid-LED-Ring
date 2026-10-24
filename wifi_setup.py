"""
Grid Ring - WiFi connection and setup portal

Two jobs:
  1. connect_with_saved() - join the WiFi network from saved config
  2. run_setup_portal()   - become a temporary WiFi access point and serve
     a small web form so the device can be set up from a phone, with no
     coding required

Setup portal flow:
  - Device creates an open WiFi network called "GridRing-Setup"
  - Connect a phone/laptop to it
  - Visit http://192.168.4.1 in a browser
  - Fill in WiFi details + display settings, submit
  - Device saves settings and restarts, joining the home WiFi network

This uses raw sockets rather than a web framework, to keep dependencies
to zero - just the MicroPython standard library.
"""

import network
import socket
import time
import machine
from config import save_config
import board
import status_light

AP_SSID = "GridRing-Setup"

# WiFi regulatory country. "GB" enables channels 12 and 13, which some UK
# routers use - without it the board may not be able to see the network.
COUNTRY = "GB"

REQUEST_TIMEOUT_S = 3      # give up on a browser connection that sends nothing
MAX_REQUEST_BYTES = 8192   # ignore anything larger than a sensible form

BUCKET_LABELS = {
    "renewable": "Green - Renewables",
    "nuclear": "Blue - Nuclear",
    "other_misc": "Purple - Other/Imports",
    "biomass": "Orange - Biomass",
    "fossil": "Red - Fossil fuels",
}
BUCKET_KEYS = list(BUCKET_LABELS.keys())


def _set_country():
    try:
        network.country(COUNTRY)
        return
    except Exception:
        pass
    try:
        import rp2               # older Pico firmware
        rp2.country(COUNTRY)
    except Exception:
        print("Note: couldn't set WiFi country - channels 12 and 13 may not be visible")


_set_country()


# ---------------------------------------------------------------------------
# Joining the saved network
# ---------------------------------------------------------------------------

def _describe_status(status):
    """Turns a WLAN status code into a readable reason, where the port provides one."""
    reasons = {}
    for name, text in (
        ("STAT_CONNECTING", "still trying to join when it gave up - usually the "
                            "password was rejected (the Pico reports a wrong "
                            "password this way), or the network's security type "
                            "isn't supported"),
        ("STAT_WRONG_PASSWORD", "wrong password"),
        ("STAT_HANDSHAKE_TIMEOUT", "the network didn't accept the password - "
                                   "check it, including capital letters"),
        ("STAT_ASSOC_FAIL", "the router refused the connection"),
        ("STAT_BEACON_TIMEOUT", "the signal was lost - check the board's aerial "
                                "and distance from the router"),
        ("STAT_NO_AP_FOUND", "network not found - check the name (it's case-sensitive) "
                             "and that it's a 2.4GHz network"),
        ("STAT_CONNECT_FAIL", "connection failed"),
    ):
        value = getattr(network, name, None)
        if value is not None:
            reasons[value] = text
    return reasons.get(status, "status code {}".format(status))


def connect_with_saved(cfg, timeout_s=60):
    """
    Attempts to join WiFi using cfg['ssid']/cfg['password']. Returns True/False.
    The generous timeout is deliberate: some routers take 15-20+ seconds to
    let a device join and hand it an IP address.
    """
    ssid = cfg.get("ssid")
    if not ssid:
        print("No saved WiFi network")
        return False

    # Make sure the setup network isn't still running in the background -
    # running both at once can stop the board joining the home network.
    network.WLAN(network.AP_IF).active(False)

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.disconnect()    # clear any half-finished attempt (the ESP32 errors otherwise)
    except OSError:
        pass
    print("Connecting to:", ssid)
    wlan.connect(ssid, cfg.get("password", ""))

    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout_s:
            print("Could not connect to '{}': {}".format(ssid, _describe_status(wlan.status())))
            wlan.active(False)
            return False
        time.sleep(0.5)

    print("Connected in {}s, IP: {}".format(time.time() - start, wlan.ifconfig()[0]))
    return True


RECONNECT_EVERY_S = 60
_last_reconnect = None


def keep_connected(cfg):
    """
    Called from the main loop. If WiFi has dropped, starts a reconnection
    attempt in the background (at most once a minute) without holding up
    the display. Returns True if currently connected.
    """
    global _last_reconnect
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return True

    now = time.ticks_ms()
    if _last_reconnect is not None:
        age = time.ticks_diff(now, _last_reconnect)
        if 0 <= age < RECONNECT_EVERY_S * 1000:
            return False
    _last_reconnect = now

    print("WiFi not connected - trying to reconnect in the background")
    try:
        wlan.active(True)
        try:
            wlan.disconnect()
        except OSError:
            pass
        wlan.connect(cfg.get("ssid", ""), cfg.get("password", ""))
    except OSError as e:
        print("Reconnect attempt failed:", e)
    return False


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _escape(text):
    """Makes text safe to put inside HTML (e.g. a password containing a quote mark)."""
    return (str(text).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _build_options(selected):
    options = ""
    for key in BUCKET_KEYS:
        sel = " selected" if key == selected else ""
        options += '<option value="{}"{}>{}</option>'.format(key, sel, BUCKET_LABELS[key])
    return options


def _render_form(cfg, message=""):
    order = cfg.get("bucket_order", BUCKET_KEYS)
    position_selects = ""
    for i in range(5):
        current = order[i] if i < len(order) else BUCKET_KEYS[i]
        position_selects += (
            '<label>Grid colour {pos} (clockwise from 12 o\'clock)'
            '<select name="pos{pos}">{options}</select></label>'
        ).format(pos=i + 1, options=_build_options(current))

    return """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grid Ring Setup</title>
<style>
body {{ font-family: sans-serif; max-width: 420px; margin: 20px auto; padding: 0 12px; }}
label {{ display: block; margin-bottom: 14px; }}
input, select {{ width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; }}
button {{ width: 100%; padding: 10px; font-size: 16px; margin-top: 8px; }}
.msg {{ background: #fee; padding: 10px; border-radius: 6px; margin-bottom: 14px; }}
h2 {{ margin-bottom: 4px; }}
</style></head>
<body>
<h2>Grid Ring Setup</h2>
<p>UK electricity generation mix, clock and pomodoro timer</p>
{message}
<form method="POST" action="/save" accept-charset="utf-8">
  <label>WiFi network name (case-sensitive, 2.4GHz only)
    <input name="ssid" value="{ssid}" required
           autocapitalize="none" autocorrect="off" autocomplete="off" spellcheck="false">
  </label>
  <label>WiFi password
    <input name="password" type="password" value="{password}"
           autocapitalize="none" autocorrect="off" spellcheck="false">
  </label>
  <label>Brightness ({brightness_pct}%)
    <input name="brightness" type="range" min="5" max="100" value="{brightness_pct}">
  </label>
  <label>Top LED (0-11) - the LED at 12 o'clock
    <input name="start_led" type="number" min="0" max="11" value="{start_led}">
  </label>
  {position_selects}
  <button type="submit">Save and connect</button>
</form>
</body></html>""".format(
        message='<p class="msg">{}</p>'.format(message) if message else "",
        ssid=_escape(cfg.get("ssid", "")),
        password=_escape(cfg.get("password", "")),
        brightness_pct=int(cfg.get("brightness", 0.3) * 100),
        start_led=cfg.get("start_led", 6),
        position_selects=position_selects,
    )


def _render_saved(ssid):
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="font-family:sans-serif;max-width:420px;margin:40px auto;'
        'padding:0 12px;text-align:center">'
        "<h2>Saved</h2><p>Restarting and connecting to <b>{}</b>&hellip;</p>"
        "<p>If it can't connect, the GridRing-Setup network will reappear "
        "after about a minute - reconnect to it and try again.</p></body></html>"
    ).format(_escape(ssid))


# ---------------------------------------------------------------------------
# HTTP handling
# ---------------------------------------------------------------------------

def _read_request(conn):
    """
    Reads one HTTP request, including the whole body of a POST.
    Browsers often send the headers and the form data in separate packets,
    so a single recv() isn't enough. Returns (method, path, body_bytes).
    """
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(512)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            break

    split = data.find(b"\r\n\r\n")
    if split == -1:
        return None, None, b""

    lines = data[:split].decode().split("\r\n")
    body = data[split + 4:]

    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None, None, b""
    method, path = parts[0], parts[1]

    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    while len(body) < content_length and len(body) < MAX_REQUEST_BYTES:
        chunk = conn.recv(512)
        if not chunk:
            break
        body += chunk

    return method, path, body


def _url_decode(value):
    """Decodes one form-encoded value, including multi-byte characters such as £."""
    value = value.replace(b"+", b" ")
    out = bytearray()
    i = 0
    while i < len(value):
        if value[i] == 37 and i + 2 < len(value):   # 37 is "%"
            try:
                out.append(int(value[i + 1:i + 3].decode(), 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(value[i])
        i += 1
    return bytes(out).decode()


def _parse_form(body):
    """Minimal application/x-www-form-urlencoded parser - no external deps."""
    fields = {}
    for pair in body.split(b"&"):
        idx = pair.find(b"=")
        if idx == -1:
            continue
        fields[_url_decode(pair[:idx])] = _url_decode(pair[idx + 1:])
    return fields


def _send_html(conn, html):
    body = html.encode()
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(len(body))
    conn.sendall(header.encode())
    conn.sendall(body)


def _handle_save(conn, cfg, body):
    """Validates and saves the submitted form. Returns True if settings were saved."""
    fields = _parse_form(body)

    # Strip stray spaces a phone keyboard may add after autocomplete
    ssid = fields.get("ssid", "").strip()
    if not ssid:
        print("Form arrived without a WiFi name - showing the form again")
        _send_html(conn, _render_form(cfg, "No WiFi name was received - please try again."))
        return False

    new_order = []
    for i in range(1, 6):
        key = fields.get("pos{}".format(i))
        if key in BUCKET_KEYS and key not in new_order:
            new_order.append(key)
    if len(new_order) != 5:
        new_order = cfg.get("bucket_order", BUCKET_KEYS)

    try:
        brightness_pct = max(5, min(100, int(fields.get("brightness", 30))))
    except ValueError:
        brightness_pct = 30
    try:
        start_led = max(0, min(11, int(fields.get("start_led", 6))))
    except ValueError:
        start_led = 6

    cfg["ssid"] = ssid
    cfg["password"] = fields.get("password", "")
    cfg["brightness"] = brightness_pct / 100
    cfg["start_led"] = start_led
    cfg["bucket_order"] = new_order
    save_config(cfg)

    # Password length only, never the password itself
    print("Saved settings for '{}' (password: {} characters)".format(ssid, len(cfg["password"])))
    _send_html(conn, _render_saved(ssid))
    return True


# ---------------------------------------------------------------------------
# Setup portal server
# ---------------------------------------------------------------------------

def run_setup_portal(cfg):
    # Switch off the home-WiFi connection first (it may be on if setup was
    # started with the button while running) - both at once can misbehave.
    network.WLAN(network.STA_IF).active(False)

    ap = network.WLAN(network.AP_IF)
    board.configure_setup_network(ap, AP_SSID)   # open network, no password
    status_light.setup_mode()

    ip = ap.ifconfig()[0]
    print("Setup portal active.")
    print("Connect to WiFi network '{}', then visit http://{}".format(AP_SSID, ip))

    addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(3)

    while True:
        conn, _ = s.accept()
        conn.settimeout(REQUEST_TIMEOUT_S)
        saved = False
        try:
            method, path, body = _read_request(conn)
            if method == "POST" and path == "/save":
                saved = _handle_save(conn, cfg, body)
            elif method:
                _send_html(conn, _render_form(cfg))
        except OSError as e:
            # Usually a browser's spare connection that never sent anything -
            # harmless, and the timeout stops it blocking real requests.
            print("Connection closed without a request:", e)
        except Exception as e:
            print("Setup server error:", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if saved:
            status_light.settings_saved()
            time.sleep(2)   # give the phone time to show the confirmation page
            s.close()
            ap.active(False)
            machine.reset()
