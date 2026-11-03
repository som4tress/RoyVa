"""Exercise HA-style tool calling with simulated devices; never contacts HA."""
import json
from pathlib import Path
import time
import urllib.request

root = Path.home() / 'llm-server'
key = (root / 'api.env').read_text().strip().split('=', 1)[1]
tools = [
    {'type': 'function', 'function': {'name': 'get_home_state', 'description': 'Read available lights, their names, rooms, entity IDs, and current states. Use this to discover IDs before controlling a device.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'turn_on', 'description': 'Turn on a light using an entity ID discovered from get_home_state.', 'parameters': {'type': 'object', 'properties': {'entity_id': {'type': 'string'}}, 'required': ['entity_id'], 'additionalProperties': False}}}
]
messages = [{'role': 'system', 'content': 'Use the supplied tools to fulfill the user request. Discover devices first. Do not invent entity IDs or claim success before receiving a successful tool result.'}, {'role': 'user', 'content': 'Turn on the den light.'}]
events = []
discovered = False
switched = False
started = time.perf_counter()
for step in range(5):
    payload = {'model': 'qwen36-agent', 'messages': messages, 'tools': tools, 'tool_choice': 'auto', 'max_tokens': 256, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}}
    request = urllib.request.Request('http://127.0.0.1:8000/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=300) as response:
        message = json.load(response)['choices'][0]['message']
    assistant = {k: message[k] for k in ('role', 'content', 'tool_calls') if message.get(k) is not None}
    messages.append(assistant)
    calls = message.get('tool_calls') or []
    if not calls:
        if not switched:
            raise RuntimeError('Model stopped before completing the simulated tool action')
        break
    for call in calls:
        name = call['function']['name']
        arguments = json.loads(call['function']['arguments'])
        if name == 'get_home_state':
            discovered = True
            result = {'lights': [{'entity_id': 'light.island', 'name': 'Island Light', 'area': 'Kitchen', 'state': 'off'}, {'entity_id': 'light.den_switch', 'name': 'Den Light', 'area': 'Den', 'state': 'off'}]}
        elif name == 'turn_on' and discovered and arguments == {'entity_id': 'light.den_switch'}:
            switched = True
            result = {'success': True, 'entity_id': 'light.den_switch', 'state': 'on', 'simulated': True}
        else:
            raise RuntimeError(f'Unexpected or invalid tool action: {name} {arguments}')
        events.append({'tool': name, 'arguments': arguments})
        messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
else:
    raise RuntimeError('Tool loop exceeded test limit')
report = {'passed': True, 'simulated_only': True, 'elapsed_seconds': round(time.perf_counter()-started, 2), 'tools': events, 'answer': messages[-1].get('content')}
(root / 'tool-flow-result.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report), flush=True)
