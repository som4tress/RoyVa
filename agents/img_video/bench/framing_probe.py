"""Probe (NOT part of the agent): do framing words fix the tiny people of the two-pass picture? Reuses the scenes of bench/two_pass_probe.py. For each scene it draws:
F1) the same scene + the framing stated; F2) F1 with the "keep the scene" wording loosened to "same background"; F3) a NEW scene drawn with room for the subjects + F2's wording.
run: python3 bench/framing_probe.py <job folder with reference/ref1..3.jpg>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from img_video import comfy, config, guard  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "runtime" / "bench" / "framing_probe"; PREV = OUT.parent / "two_pass_probe"
STYLE = "Cinematic photographic realism"
MAN = "white shirt, khaki cargo pants, dark shoes"; WOMAN = "red dress, red tights, black boots, black leather gloves"
SCENES = [  # tag, photo, how the people are placed, the room-for-people scene for pass 1
    ("street", 2, "walking hand in hand toward the camera", "A Parisian cobblestone street at golden hour seen from a low camera close to the ground, shallow depth of field, a clear open space in the centre foreground, buildings softly blurred behind, no people"),
    ("cafe", 3, "sitting at the small table, he holds her hand", "A Parisian cafe terrace in light rain seen from close, a small round table with two chairs filling the centre foreground, wet cobblestones, shallow depth of field, no people"),
    ("bridge", 1, "he kneels and holds her hands while she gasps with joy", "A Paris bridge at night seen from a low camera close to the ground, the river and city lights softly blurred behind, a clear open space in the centre foreground, no people"),
]
FRAME = "Medium full-body shot, the couple fills the centre of the frame, two thirds of its height, eye level."


def main(job):
    cfg, _ = config.load(); base, c = cfg["comfy"]["url"], cfg["comfy"]; clause = cfg["policy"].get("image_text", ""); cap = cfg["limits"]["image_prompt_chars"]; OUT.mkdir(parents=True, exist_ok=True); size = (864, 480); lines = []
    def final(text, style=STYLE): return ", ".join(p for p in (text.rstrip(". "), style, clause) if p)
    def p2(placing, keep, frame=True):
        t = f"{placing[:1].upper() + placing[1:]}: the man (left) and woman (right) of reference image 2 in the scene of reference image 1. " + (FRAME + " " if frame else "") + f"Man: {MAN}. Woman: {WOMAN}. " + keep
        f = final(t, ""); assert len(f) <= cap, (len(f), t); return f
    with guard.gpu_lock(wait_s=300, log=print):
        comfy.wait_until_free(base, log=print); photos = {k: comfy.upload(base, (Path(job) / "reference" / f"ref{k}.jpg").read_bytes(), f"ref_probe3_photo{k}.jpg") for k in (1, 2, 3)}
        for tag, ph, placing, room_scene in SCENES:
            seed = 4242 + ph; old = comfy.upload(base, (PREV / f"{tag}_B_scene.png").read_bytes(), f"ref_probe3_oldscene_{tag}.png")
            for name, scene, keep in (("F1", old, "Keep the scene of image 1; only the people come from image 2."), ("F2", old, "Same background; only the people from image 2.")):
                prompt = p2(placing, keep); png, t = comfy.generate_image(base, c, prompt, *size, seed, refs=[scene, photos[ph]]); (OUT / f"{tag}_{name}.png").write_bytes(png); lines.append(f"{tag} {name} pass2 {t:.1f}s ({len(prompt)} chars)"); print(lines[-1])
            p1 = final(room_scene); png1, t1 = comfy.generate_image(base, c, p1, *size, seed); (OUT / f"{tag}_F3_scene.png").write_bytes(png1)
            new = comfy.upload(base, png1, f"ref_probe3_newscene_{tag}.png"); prompt = p2(placing, "Same background; only the people from image 2.")
            png, t2 = comfy.generate_image(base, c, prompt, *size, seed, refs=[new, photos[ph]]); (OUT / f"{tag}_F3.png").write_bytes(png); lines.append(f"{tag} F3 pass1 {t1:.1f}s + pass2 {t2:.1f}s = {t1 + t2:.1f}s"); print(lines[-1])
    (OUT / "timings.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
