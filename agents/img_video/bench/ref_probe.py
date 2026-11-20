"""Probe: does Qwen-Image 2.1 keep one person across different scenes when given a reference photo? (run: python3 bench/ref_probe.py [photo.png])
Without an argument it first draws a SYNTHETIC portrait (not a real person) and uses that as the reference. Writes runtime/bench/ref_probe/*.png and prints seconds per picture; sending the pictures to the chat is a separate step (bench/send_photo.mjs)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from img_video import comfy, config, guard  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "runtime" / "bench" / "ref_probe"
PORTRAIT = ("Studio portrait photograph of a friendly 30-year-old man, short wavy brown hair, light stubble, thin round glasses, neutral grey background, looking at the camera, natural soft light, sharp focus")
SCENES = [
    ("walk", "The person from the reference photo walking along a cobblestone street in Paris at golden hour, wearing a navy trench coat and a red beret, the Eiffel Tower far behind him, full body shot, cinematic photo"),
    ("cafe", "The person from the reference photo sitting at a sidewalk cafe table in rainy Paris holding a coffee cup, wearing a navy trench coat and a red beret, medium shot, cinematic photo"),
    ("bridge", "The person from the reference photo crossing a Paris bridge at night, city lights reflecting on the river, wearing a navy trench coat and a red beret, looking over his shoulder, cinematic photo"),
    ("flowers", "Close-up of the person from the reference photo smiling at a flower stall on a Paris street in soft morning light, wearing a navy trench coat and a red beret, cinematic photo"),
]


def main():
    cfg, _ = config.load(); base, c = cfg["comfy"]["url"], cfg["comfy"]; OUT.mkdir(parents=True, exist_ok=True); size = (768, 432)
    with guard.gpu_lock(wait_s=300, log=print):
        comfy.wait_until_free(base, log=print)
        if len(sys.argv) > 1: ref_png = Path(sys.argv[1]).read_bytes(); print("reference: the photo given on the command line")
        else:
            ref_png, secs = comfy.generate_image(base, c, PORTRAIT, 768, 768, 424242); print(f"synthetic reference portrait drawn in {secs:.1f}s")
        (OUT / "reference.png").write_bytes(ref_png)
        name = comfy.upload(base, ref_png, "ref_probe_person.png"); print("uploaded as", name)
        for tag, prompt in SCENES:
            png, secs = comfy.generate_image(base, c, prompt, *size, 1234, refs=[name]); (OUT / f"{tag}.png").write_bytes(png); print(f"{tag:8s} with reference: {secs:.1f}s ({len(prompt)} chars)")
        png, secs = comfy.generate_image(base, c, SCENES[0][1].replace("The person from the reference photo", "A man"), *size, 1234); (OUT / "walk_no_ref.png").write_bytes(png); print(f"walk_no_ref (no reference, same size): {secs:.1f}s")


if __name__ == "__main__":
    main()
