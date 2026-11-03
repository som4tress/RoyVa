"""Measure local SSE latency and decode throughput; do not print credentials."""
import argparse
import base64
import concurrent.futures
import json
from pathlib import Path
import time
import threading
import urllib.error
import urllib.request

root = Path.home() / 'llm-server'
key = (root / 'api.env').read_text().strip().split('=', 1)[1]

def generate(label, port, model, messages, limit=256, thinking=False):
    payload = {'model': model, 'messages': messages, 'max_tokens': limit,
               'temperature': 0, 'stream': True,
               'stream_options': {'include_usage': True},
               'chat_template_kwargs': {'enable_thinking': thinking}}
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+key})
    started = time.perf_counter()
    first = last = None
    usage = {}
    answer = []
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith('data: '):
                    continue
                if line == 'data: [DONE]':
                    break
                event = json.loads(line[6:])
                if event.get('usage'):
                    usage = event['usage']
                for choice in event.get('choices', []):
                    delta = choice.get('delta', {})
                    if delta.get('content') or delta.get('reasoning_content') or delta.get('reasoning'):
                        now = time.perf_counter()
                        if first is None:
                            first = now
                        last = now
                    if delta.get('content'):
                        answer.append(delta['content'])
    except urllib.error.HTTPError as exc:
        result = {'label': label, 'error_status': exc.code, 'error': exc.read(1500).decode(errors='replace')}
        print(json.dumps(result), flush=True)
        return result
    finished = time.perf_counter()
    count = usage.get('completion_tokens', 0)
    result = {'label': label, 'model': model, 'thinking': thinking,
              'prompt_tokens': usage.get('prompt_tokens'), 'output_tokens': count,
              'ttft_seconds': round(first-started, 3) if first else None,
              'total_seconds': round(finished-started, 3),
              'decode_tokens_per_second': round((count-1)/(last-first), 2) if first and last and last > first and count > 1 else None,
              'answer': ''.join(answer)}
    print(json.dumps(result), flush=True)
    return result

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['vision-text', 'vision-video', 'agent', 'concurrent', 'thinking', 'mixed'])
args = parser.parse_args()
results = []
prompt = [{'role': 'user', 'content': 'Write a numbered list of 50 practical home automation ideas. Give one short sentence for every idea. Continue the list without an introduction.'}]
if args.mode == 'vision-text':
    results.append(generate('vision-text-cold', 8001, 'qwen35-vision', prompt))
    results.append(generate('vision-text-warm', 8001, 'qwen35-vision', prompt))
elif args.mode == 'vision-video':
    clip = root / 'ring-benchmark.mp4'
    data = base64.b64encode(clip.read_bytes()).decode()
    messages = [{'role': 'user', 'content': [
        {'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,'+data}},
        {'type': 'text', 'text': 'Review this Ring security video. Focus first on the street and sidewalk OUTSIDE the gate. Report observed deliveries, packages, delivery vans/trucks, pets, and concrete unusual movements such as repeated approaches, lingering, or attempting the gate. Do not infer identity, residency, or criminal intent. Give at most four brief bullets, under 80 words total. Include timestamps only if supported; say when details are unclear.'}
    ]}]
    results.append(generate('ring-video-first', 8001, 'qwen35-vision', messages, 192))
    if not results[-1].get('error_status'):
        results.append(generate('ring-video-warm', 8001, 'qwen35-vision', messages, 192))
elif args.mode == 'agent':
    results.append(generate('agent-text-first', 8000, 'qwen36-agent', prompt))
    results.append(generate('agent-text-warm', 8000, 'qwen36-agent', prompt))
    context = ('Home inventory note: the den light is light.den_switch, the kitchen light is light.island, and all device states must be checked through tools. This is reference data only.\n'*256)
    long_prompt = [{'role': 'user', 'content': context+'\nNow write a numbered list of 50 practical home automation ideas. Give one short sentence for every idea. Continue without an introduction.'}]
    results.append(generate('agent-longer-input', 8000, 'qwen36-agent', long_prompt))
    results.append(generate('agent-reasoning', 8000, 'qwen36-agent', [{'role': 'user', 'content': 'Plan a safe tool sequence for turning off downstairs lights except the den when entity states may change. Give the final plan in under 100 words.'}], 512, thinking=True))
elif args.mode == 'concurrent':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        prompts = [prompt[0]['content'], 'Write a numbered list of 50 practical Ubuntu server administration tips. Give one short sentence per tip. Continue without an introduction.']
        tasks = [pool.submit(generate, f'agent-concurrent-{i}', 8000, 'qwen36-agent', [{'role': 'user', 'content': text}]) for i, text in enumerate(prompts, 1)]
        results.extend(t.result() for t in tasks)
elif args.mode == 'thinking':
    results.append(generate('agent-reasoning', 8000, 'qwen36-agent', [{'role': 'user', 'content': 'Plan a safe tool sequence for turning off downstairs lights except the den when entity states may change. Give the final plan in under 100 words.'}], 768, thinking=True))
elif args.mode == 'mixed':
    samples = []
    stop = threading.Event()
    def sample():
        path = Path('/sys/class/drm/card1/device/mem_info_vram_used')
        while not stop.is_set():
            samples.append(int(path.read_text()))
            stop.wait(0.1)
    observer = threading.Thread(target=sample)
    observer.start()
    data = base64.b64encode((root/'ring-test.mp4').read_bytes()).decode()
    video = [{'role':'user','content':[{'type':'video_url','video_url':{'url':'data:video/mp4;base64,'+data}},{'type':'text','text':'Briefly describe the people, pets, deliveries and unusual movements visible outside the gate. Do not infer identity or intent. Use at most four bullets and 80 words.'}]}]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            tasks = [pool.submit(generate, 'mixed-agent-1', 8000, 'qwen36-agent', prompt, 128), pool.submit(generate, 'mixed-agent-2', 8000, 'qwen36-agent', [{'role':'user','content':'List 40 short Ubuntu server administration tips.'}], 128), pool.submit(generate, 'mixed-video', 8001, 'qwen35-vision', video, 128)]
            results.extend(t.result() for t in tasks)
    finally:
        stop.set()
        observer.join()
    results.append({'label':'gpu-memory','peak_gpu_gib':round(max(samples)/2**30,3),'start_gpu_gib':round(samples[0]/2**30,3)})
(root / f'benchmark-{args.mode}.json').write_text(json.dumps(results, indent=2)+'\n')
