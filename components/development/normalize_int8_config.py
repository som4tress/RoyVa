"""Describe an AutoRound auto_gptq-packed checkpoint with standard GPTQ metadata."""
import json
from pathlib import Path

root = Path.home() / 'llm-server/int8-candidate'
path = root / 'config.json'
original = root / 'config.autoround-original.json'
if not original.exists():
    original.write_bytes(path.read_bytes())
config = json.loads(original.read_text())
quant = config['quantization_config']
if quant.get('packing_format') != 'auto_round:auto_gptq' or quant.get('bits') != 8:
    raise RuntimeError('Expected an 8-bit auto_gptq-packed checkpoint')
index = json.loads((root / 'model.safetensors.index.json').read_text())['weight_map']
lm_head_quantized = any(k.endswith('lm_head.qweight') for k in index)
dynamic = {}
for pattern, settings in quant.get('extra_config', {}).items():
    if settings.get('bits', 8) >= 16:
        dynamic['-:' + pattern] = {}
    elif settings.get('bits', 8) != 8:
        raise RuntimeError('Unexpected mixed quantization precision')
config['quantization_config'] = {
    'quant_method': 'gptq', 'bits': 8,
    'group_size': quant['group_size'], 'desc_act': False,
    'sym': quant['sym'], 'lm_head': lm_head_quantized,
    'checkpoint_format': 'gptq', 'dynamic': dynamic,
}
path.write_text(json.dumps(config, indent=2) + '\n')
print('Standard GPTQ INT8 metadata prepared; full-precision exclusions:', len(dynamic), 'quantized lm_head:', lm_head_quantized)
