"""Losslessly repeat per-channel GPTQ scales/zeros into 128-wide groups.

Quantized integer weight codes are never changed. Original verified shards are
retained separately. Only index-listed safetensors are read; no model code runs.
"""
import json
import os
from pathlib import Path
import shutil
import time
import torch
from safetensors import safe_open
from safetensors.torch import save_file

source = Path('/workspace/int8-candidate')
target = Path('/workspace/int8-gptq-g128')
target.mkdir(exist_ok=True)
os.chown(target, 1000, 1000)
index = json.loads((source / 'model.safetensors.index.json').read_text())
mapping = index['weight_map']
shards = sorted(set(mapping.values()))
deadline = time.monotonic() + 7200
total_size = 0
checked = 0
for shard in shards:
    src = source / shard
    while not src.exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Timed out waiting for verified model shard')
        time.sleep(3)
    out = target / shard
    marker = target / (shard + '.complete.json')
    if out.exists() and marker.exists():
        info = json.loads(marker.read_text())
        total_size += info['tensor_bytes']
        checked += info['checked_layers']
        continue
    tensors = {}
    shard_checked = 0
    with safe_open(src, framework='pt', device='cpu') as handle:
        keys = list(handle.keys())
        def get(key):
            if mapping.get(key) == shard:
                return handle.get_tensor(key)
            other = source / mapping[key]
            while not other.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Timed out waiting for paired tensor shard')
                time.sleep(3)
            with safe_open(other, framework='pt', device='cpu') as reader:
                return reader.get_tensor(key)
        for key in keys:
            value = handle.get_tensor(key)
            if key.endswith(('.scales', '.qzeros', '.g_idx')):
                prefix = key.rsplit('.', 1)[0]
                weight_key = prefix + '.qweight'
                if weight_key in mapping:
                    weight = get(weight_key)
                    if weight.dtype != torch.int32 or weight.ndim != 2:
                        raise RuntimeError(f'Unexpected GPTQ packing: {key}')
                    input_features = weight.shape[0] * 4
                    if input_features % 128:
                        raise RuntimeError(f'Input dimension not divisible by 128: {key}')
                    groups = input_features // 128
                    if key.endswith('.g_idx'):
                        if value.numel() != input_features or torch.count_nonzero(value):
                            raise RuntimeError(f'Expected per-channel, non-reordered g_idx: {key}')
                        value = torch.arange(input_features, dtype=value.dtype) // 128
                    else:
                        if value.ndim != 2 or value.shape[0] != 1:
                            raise RuntimeError(f'Expected one per-channel group: {key} {value.shape}')
                        expanded = value.repeat(groups, 1)
                        if not torch.equal(expanded, value.expand_as(expanded)):
                            raise RuntimeError('Scale/zero replication check failed')
                        if key.endswith('.scales'):
                            # Check scale lookup across every original input row.
                            selected = expanded[torch.arange(input_features)//128]
                            if not torch.equal(selected, value.expand(input_features, -1)):
                                raise RuntimeError('Grouped dequantization scale lookup changed')
                            shard_checked += 1
                        value = expanded
            tensors[key] = value.contiguous()
        tensor_bytes = sum(t.numel()*t.element_size() for t in tensors.values())
        temporary = target / (shard + '.partial')
        save_file(tensors, str(temporary), metadata={'format': 'pt'})
        temporary.rename(out)
        marker.write_text(json.dumps({'tensor_bytes': tensor_bytes, 'checked_layers': shard_checked}))
        os.chown(out, 1000, 1000)
        os.chown(marker, 1000, 1000)
    tensors.clear()
    total_size += tensor_bytes
    checked += shard_checked
    print('Converted:', shard, 'verified scale lookups:', shard_checked, flush=True)
for path in source.iterdir():
    if path.name in ('config.json', 'model.safetensors.index.json'):
        continue
    if path.suffix in ('.json', '.jinja') and path.name not in ('quantization_config.json', 'config.autoround-original.json'):
        shutil.copy2(path, target / path.name)
config = json.loads((source / 'config.json').read_text())
if config['quantization_config']['group_size'] != 128:
    raise RuntimeError('Output config must describe group_size 128')
(target / 'config.json').write_text(json.dumps(config, indent=2)+'\n')
index.setdefault('metadata', {})['total_size'] = total_size
(target / 'model.safetensors.index.json').write_text(json.dumps(index, indent=2)+'\n')
(target / 'conversion.json').write_text(json.dumps({'operation': 'per-channel INT8 GPTQ to repeated group_size=128 scales and zero points', 'integer_weights_changed': False, 'checked_layers': checked, 'tensor_bytes': total_size}, indent=2)+'\n')
for path in target.iterdir():
    os.chown(path, 1000, 1000)
print('CONVERSION COMPLETE:', checked, 'quantized layers checked;', total_size, 'tensor bytes', flush=True)
