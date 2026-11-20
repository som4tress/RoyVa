"""Probe (NOT part of the agent): is drawing a picture in TWO passes better than one? Pass 1 draws the scene only; pass 2 takes that picture and a photo as references and puts the people in.
For each of 3 scenes it draws: A) the current way (one pass, photo as reference, composer prompt), B) the scene only, C) the two-pass result. Prints seconds per render. run: python3 bench/two_pass_probe.py <job folder with reference/ref1..3.jpg>"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from img_video import comfy, compose, config, guard  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "runtime" / "bench" / "two_pass_probe"
STYLE = "Cinematic photographic realism"
MAN = "short dark hair, beard, white shirt, khaki cargo pants, dark shoes"
WOMAN = "long dark hair, red dress, red tights, black boots, black leather gloves"
SCENES = [  # (tag, photo number, action, where, empty scene for pass 1, how the people are placed in pass 2)
    ("street", 2, "They stroll hand in hand toward the camera", "Parisian cobblestone street, golden hour", "An empty Parisian cobblestone street at golden hour with Haussmann buildings, warm backlight and long shadows, no people",
     "walking hand in hand toward the camera"),
    ("cafe", 3, "They sit at a small table, he holds her hand", "Parisian cafe terrace in light rain", "An empty Parisian cafe terrace in light rain, a small round table with two chairs, wet cobblestones, warm lights, no people",
     "sitting at the small table, he holds her hand"),
    ("bridge", 1, "He kneels and holds her hands, she gasps with joy", "Pont des Arts at night, city lights", "An empty Paris bridge at night with the river and city lights reflecting on the water, no people",
     "he kneels and holds her hands while she gasps with joy"),
]


def main(job):
    cfg, _ = config.load(); base, c = cfg["comfy"]["url"], cfg["comfy"]; clause = cfg["policy"].get("image_text", ""); cap = cfg["limits"]["image_prompt_chars"]; OUT.mkdir(parents=True, exist_ok=True); size = (864, 480); rows = []
    def final(text, style=STYLE): return ", ".join(p for p in (text.rstrip(". "), style, clause) if p)
    with guard.gpu_lock(wait_s=300, log=print):
        comfy.wait_until_free(base, log=print); photos = {}
        for k in (1, 2, 3): photos[k] = comfy.upload(base, (Path(job) / "reference" / f"ref{k}.jpg").read_bytes(), f"ref_probe2_photo{k}.jpg")
        for tag, ph, action, where, empty, placing in SCENES:
            seed = 4242 + ph
            people = [{"label": "Man (left in reference image 1)", "outfit": MAN}, {"label": "Woman (right in reference image 1)", "outfit": WOMAN}]
            a = compose.compose(people, action, [where], "", [("look", STYLE)], cap, len(clause), "Only the people come from the references.", [MAN, WOMAN])
            pa = final(a["prompt"], a["style"]); png, ta = comfy.generate_image(base, c, pa, *size, seed, refs=[photos[ph]]); (OUT / f"{tag}_A_one_pass.png").write_bytes(png)
            p1 = final(empty); png1, t1 = comfy.generate_image(base, c, p1, *size, seed); (OUT / f"{tag}_B_scene.png").write_bytes(png1)
            scene = comfy.upload(base, png1, f"ref_probe2_scene_{tag}.png")
            p2 = final(f"Put the man (left) and the woman (right) from reference image 2 into the scene of reference image 1, {placing}. Man: {MAN}. Woman: {WOMAN}. Keep the street, light and buildings of reference image 1; take only the two people from reference image 2.", "")
            png2, t2 = comfy.generate_image(base, c, p2, *size, seed, refs=[scene, photos[ph]]); (OUT / f"{tag}_C_two_pass.png").write_bytes(png2)
            rows.append((tag, ph, len(pa), len(p1), len(p2), ta, t1, t2)); print(f"{tag:7s} photo {ph} | prompt chars A {len(pa)} B {len(p1)} C {len(p2)} | one-pass {ta:.1f}s | pass1 {t1:.1f}s + pass2 {t2:.1f}s = {t1 + t2:.1f}s")
    (OUT / "timings.txt").write_text("\n".join(f"{r[0]} photo{r[1]} A={r[5]:.1f}s pass1={r[6]:.1f}s pass2={r[7]:.1f}s two_pass_total={r[6] + r[7]:.1f}s" for r in rows) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
