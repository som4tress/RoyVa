#!/usr/bin/env python3
"""Play a radio stream on every Sonos player on the LAN, with proper DIDL metadata.

Usage: sonos_play_all.py "<stream-url>" ["<title>"]
"""
import html
import sys
import soco
from soco.exceptions import SoCoUPnPException

URL = sys.argv[1]
TITLE = sys.argv[2] if len(sys.argv) > 2 else "Radio"

DIDL = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
    'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
    'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
    '<item id="-1" parentID="-1" restricted="true">'
    f"<dc:title>{html.escape(TITLE)}</dc:title>"
    "<upnp:class>object.item.audioItem.radio</upnp:class>"
    f'<res protocolInfo="http-get:*:audio/mpeg:*">{html.escape(URL)}</res>'
    "</item></DIDL-Lite>"
)

zones = soco.discover(timeout=10)
if not zones:
    print("no Sonos players found")
    sys.exit(1)

ok = 0
for z in sorted(zones, key=lambda x: x.player_name):
    try:
        z.play_uri(URL, DIDL)
        print(f"OK    {z.player_name:14} {z.ip_address}")
        ok += 1
    except SoCoUPnPException as e:
        print(f"FAIL  {z.player_name:14} {z.ip_address}  {str(e)[:120]}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {z.player_name:14} {z.ip_address}  {type(e).__name__}: {str(e)[:100]}")

print(f"\n{ok}/{len(zones)} players started")
