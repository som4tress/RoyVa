"""Runs inside the Chatterbox venv (it needs torch and chatterbox, which the agent itself does not): storyboard.json -> say<i>.wav next to it, on this machine's CPU.
usage: <venv python> voice_worker.py <storyboard.json> <exaggeration> <cfg_weight>"""
import json
import sys
import time
from pathlib import Path

import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

sb_path, exag, cfgw = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
sb = json.loads(sb_path.read_text()); t0 = time.time()
m = ChatterboxTTS.from_pretrained(device="cpu")
for s in sb["shots"]:
    t = time.time(); w = m.generate(s["narration"], exaggeration=exag, cfg_weight=cfgw)
    ta.save(str(sb_path.parent / f"say{s['i']}.wav"), w, m.sr)
    print(json.dumps({"shot": s["i"], "chars": len(s["narration"]), "audio_s": round(w.shape[-1] / m.sr, 2), "secs": round(time.time() - t, 1)}), flush=True)
print(json.dumps({"voice_total": round(time.time() - t0, 1)}), flush=True)
