"""Read Home Assistant area/floor/device/entity registries for report scoping."""
import json, os, re
from pathlib import Path
import ha_ws


def _connection():
    cfg = json.loads((Path.home() / '.config/opencode/opencode.json').read_text())
    ha = cfg['mcp']['servers']['home-assistant']
    if ha.get('type') == 'local':
        ha = json.loads((Path.home() / 'llm-server/ha-remote.json').read_text())
    auth = ha.get('headers', {}).get('Authorization', '')
    missing = []

    def substitute(m):
        v = os.environ.get(m[1])
        if not v:
            missing.append(m[1])
        return v or ''

    auth = re.sub(r'\{env:([^}]+)\}', substitute, auth)
    if missing or not auth:
        raise ValueError('Home Assistant authentication environment is unavailable.')
    base = ha['url'].split('/api/')[0]
    ws_url = base.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/websocket'
    token = auth.split(' ', 1)[1] if auth.lower().startswith('bearer ') else auth
    return ws_url, token


def snapshot():
    """Return {area_id: {...}, floor_id: {...}, devices, entities} from the registries."""
    ws_url, token = _connection()
    cmds = [
        {'id': 1, 'type': 'config/area_registry/list'},
        {'id': 2, 'type': 'config/floor_registry/list'},
        {'id': 3, 'type': 'config/device_registry/list'},
        {'id': 4, 'type': 'config/entity_registry/list'},
    ]
    raw = ha_ws.call(ws_url, token, cmds)
    return {
        'areas': {a['area_id']: a for a in raw[1] or []},
        'floors': {f['floor_id']: f for f in raw[2] or []},
        'devices': {d['id']: d for d in raw[3] or []},
        'entities': {e['entity_id']: e for e in raw[4] or []},
    }
