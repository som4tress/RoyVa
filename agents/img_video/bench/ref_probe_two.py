"""Probe: can Qwen-Image 2.1 keep TWO different people apart in one picture when each has its own reference photo? Draws two SYNTHETIC portraits (not real people), uses both as references, and draws
couple scenes in Paris with three prompt styles. Writes runtime/bench/ref_probe_two/*.png and prints seconds. (run: python3 bench/ref_probe_two.py)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from img_video import comfy, config, guard  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "runtime" / "bench" / "ref_probe_two"
MAN = "Studio portrait photograph of a friendly 35-year-old man, short dark hair, light stubble, warm brown eyes, neutral grey background, looking at the camera, natural soft light, sharp focus"
WOMAN = "Studio portrait photograph of a cheerful 33-year-old woman, shoulder-length wavy auburn hair, green eyes, light freckles, neutral grey background, looking at the camera, natural soft light, sharp focus"
SCENES = [
    ("a_walk", "The man from the first reference photo and the woman from the second reference photo walk side by side along a Paris street at golden hour, he wears a white shirt and khaki pants, she wears a red dress and a black leather jacket, the Eiffel Tower behind them, full body, cinematic photo"),
    ("b_seine", "Wide shot of the man from reference image 1 and the woman from reference image 2 strolling hand in hand along the Seine in Paris, he in a white shirt and khaki pants, she in a red dress with a black leather jacket and boots, warm evening light, cinematic photo"),
    ("c_cafe", "Two people sit at a sidewalk cafe table in Paris: the man from the first photo (white shirt) on the left and the woman from the second photo (red dress, black leather jacket) on the right, smiling at each other, medium shot, cinematic photo"),
    ("d_solo_man", "The man from the first reference photo alone, walking along a Paris street at golden hour in a white shirt and khaki pants, cinematic photo"),
]


def main():
    cfg, _ = config.load(); base, c = cfg["comfy"]["url"], cfg["comfy"]; OUT.mkdir(parents=True, exist_ok=True); size = (768, 432)
    with guard.gpu_lock(wait_s=300, log=print):
        comfy.wait_until_free(base, log=print); names = []
        for tag, prompt, seed in (("man", MAN, 111), ("woman", WOMAN, 222)):
            png, secs = comfy.generate_image(base, c, prompt, 768, 768, seed); (OUT / f"ref_{tag}.png").write_bytes(png); names.append(comfy.upload(base, png, f"ref_probe_{tag}.png")); print(f"synthetic {tag} drawn in {secs:.1f}s")
        for tag, prompt in SCENES:
            refs = names[:1] if tag == "d_solo_man" else names
            png, secs = comfy.generate_image(base, c, prompt, *size, 1234, refs=refs); (OUT / f"{tag}.png").write_bytes(png); print(f"{tag:11s} {len(refs)} reference(s): {secs:.1f}s ({len(prompt)} chars)")


if __name__ == "__main__":
    main()
