"""Picture check: does the rendered picture match what it was meant to show? Two steps, because asking "does it match?" directly makes the model agree too easily:
1. describe the picture factually without knowing the intent (objects, colors, positions, which way figures face); 2. compare that description with the intent, strictly.
On a mismatch the description is rewritten to state the failing details explicitly, and the picture is drawn again (see pipeline.images). Runs on the local model only."""
from . import llm


def check(c, png, prompt, caption):
    """(ok, problems)."""
    desc = llm.ask_about_image(c, png, "Describe this picture factually and in detail without interpreting it: every object, its color, its position (left/right/center, foreground/background), "
                               "any text or lettering you can read (and whether it is garbled), and for every person or animal which way it faces (toward the viewer, away from the viewer, left, right) "
                               "and whether we see its face or its back. Plain text.", max_tokens=500)
    o = llm.ask_json(c, "You compare an intended picture with a factual description of the picture that was actually drawn.",
        f"The picture was supposed to show: {prompt}\nIt must illustrate this statement: {caption}\n\nFactual description of the actual picture:\n{desc}\n\n"
        "Compare point by point (objects, colors, directions, who faces what, positions, garbled or unwanted text). Be strict: a wrong direction, wrong color or missing object is a problem. "
        "Return JSON: {\"matches\": true or false, \"problems\": [short, specific mismatches; empty if none]}", temperature=0.1,
        check=lambda o: None if isinstance(o.get("matches"), bool) and isinstance(o.get("problems", []), list) else "need matches (boolean) and problems (list)")
    problems = [str(x)[:200] for x in o.get("problems", [])][:5]
    return (bool(o["matches"]) and not problems), problems


def fix_prompt(c, prompt, caption, problems):
    """The same picture idea, rewritten so the details that came out wrong are stated explicitly."""
    o = llm.ask_json(c, "You rewrite a picture description so an image model draws it correctly.",
        f"Picture description: {prompt}\nIt must illustrate: {caption}\nWhen it was drawn, these things were wrong: " + "; ".join(problems) + "\n\n"
        "Rewrite the description so that each wrong thing is stated explicitly and unambiguously (exact colors, positions, which way figures face, direction of lines), keeping the same idea; "
        "under 80 words, English. Return JSON: {\"image_prompt\": \"...\"}", temperature=0.4, check=lambda o: None if isinstance(o.get("image_prompt"), str) and len(o["image_prompt"]) > 20 else "need image_prompt")
    return o["image_prompt"].strip()
