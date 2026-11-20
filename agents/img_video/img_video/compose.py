"""Writes the final picture description of ONE picture under the hard character cap (the 3090 must never get more than the cap) without losing what matters.

Every part of the description is a fact with a priority. MUST: the person tags that tie a reference image to a person, what the user stated (their outfits, the place, the action), the shot's main action.
SHOULD: the director's own details of the people and the look of the style. NICE: the director's framing, colors, palette, lighting, camera words. When the text is too long the least valuable WHOLE facts are dropped first (nice, then should); a MUST is never dropped
and nothing is cut in the middle of an item. Only if the musts alone do not fit, they are rewritten shorter (`fix`, the LLM) or, as the very last resort, shortened at a word boundary. Pure functions: nothing here calls a model or the server unless `fix` is given."""
import re

WORD = re.compile(r"[a-z0-9]+")
DANGLING = re.compile(r"(?:\s+(?:in|on|at|of|to|from|with|and|or|the|a|an|by|for|as|into|onto|while|that|his|her|its|their|over|under))+$", re.I)


STOP = frozenset("a an the of in on at to and or with for from by as is are was were be been it its his her their them they he she we you i me my our your this that these those there here into onto while over under up down out off than then so but not no all both each every any some one two".split())


def words(text):
    """The meaningful words of a phrase (lowercase, without function words), so that two phrases that only share "of" or "the" do not count as the same thing."""
    return set(WORD.findall(str(text).lower())) - STOP


def items_of(text):
    """"Khaki cargo pants, white shirt; dark shoes" -> ["Khaki cargo pants", "white shirt", "dark shoes"] (an item is a comma or semicolon separated phrase)."""
    return [x.strip(" .") for x in re.split(r"[,;]", str(text or "")) if x.strip(" .")]


def cut_items(text, n):
    """The first whole items of a comma separated text that fit in n characters ("a, b, c" -> "a, b"): an outfit loses its last item, never half of one. The first item is kept (cut at a word boundary) even when it alone is too long."""
    its = items_of(text); out = []
    for it in its:
        if len(", ".join(out + [it])) <= n: out.append(it)
        else: break
    return ", ".join(out) if out else cut(" ".join(str(text).split()), n)


def cut(text, n):
    """At most n characters, at a word boundary, never ending on a word a phrase cannot end on."""
    text = " ".join(str(text).split())
    if len(text) <= n: return text
    t = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-") if " " in text[:n] else text[:n]
    t2 = DANGLING.sub("", t).rstrip(" ,;:-")
    return t2 if len(t2) >= min(8, len(t)) else t


def _render(people, clause, subject, setting, colors, style):
    blocks = []
    for pe in people:
        its = [t for t, _p, _r in pe["items"]]
        blocks.append(pe["label"] + (": " + ", ".join(its) if its else "") + ".")
    if clause and people: blocks.append(clause)
    if subject: blocks.append(subject.strip().rstrip(".") + ".")
    if setting: blocks.append("Setting: " + ", ".join(t for t, _p, _r in setting) + ".")
    if colors: blocks.append("Colors: " + colors[0].strip(" .") + ".")
    return " ".join(blocks), ", ".join(t for _n, t, _p, _r in style)


def total_len(prompt, style, clause_len):
    """The length the picture stage sends: description, then the style, then the policy clause, joined with ', ' (see pipeline._images)."""
    return len(prompt.rstrip(". ")) + (2 + len(style) if style else 0) + (2 + clause_len if clause_len else 0)


def compose(people, subject, setting, colors, style, cap, clause_len=0, ref_clause="", stated=(), fix=None):
    """people: [{"label": "Ann (left in reference image 1)", "outfit": "red dress, black boots"}]; subject: the shot's action; setting: [where, framing...] (the first is the place and must stay); colors: text or "";
    style: [(name, text)] in the order they are written (the first is the look); stated: phrases the user's own request states. `fix(text, room)` rewrites the musts shorter when they alone do not fit.
    Returns {"prompt", "style", "dropped": [what was left out], "fixed": bool, "length"}."""
    sw = set()
    for ph in stated: sw |= words(ph)
    def prio(text, base):                                     # a detail the user stated is a MUST; the director's own stays at `base`
        return 0 if words(text) & sw else base
    P = [{"label": pe["label"], "items": [(t, prio(t, 1), 40 - k) for k, t in enumerate(items_of(pe.get("outfit")))]} for pe in people]      # later items are dropped first
    S = [(t, 0 if k == 0 else prio(t, 2), 20 - k) for k, t in enumerate(setting or []) if t]                                                    # the place first and always
    C = (colors, prio(colors, 2), 5) if colors else None
    ST = [(n, it, prio(it, 1 if k == 0 else 2), 10 - k - j / 10) for k, (n, t) in enumerate(style or []) if t for j, it in enumerate(items_of(t))]       # the look is worth more than palette, lighting, camera; a style item the user stated is a MUST
    dropped = []
    def build(): return _render(P, ref_clause, subject, S, C, ST)
    def over(): pr, st = build(); return total_len(pr, st, clause_len) > cap
    while over():
        cands = [(-p, r, ("o", i, j)) for i, pe in enumerate(P) for j, (_t, p, r) in enumerate(pe["items"]) if p > 0]
        cands += [(-p, r, ("s", j)) for j, (_t, p, r) in enumerate(S) if p > 0]
        cands += [(-C[1], C[2], ("c",))] if C and C[1] > 0 else []
        cands += [(-p, r, ("y", j)) for j, (_n, _t, p, r) in enumerate(ST) if p > 0]
        if not cands: break
        _p, _r, key = sorted(cands)[0]
        if key[0] == "o": dropped.append(P[key[1]]["items"].pop(key[2])[0])
        elif key[0] == "s": dropped.append(S.pop(key[1])[0])
        elif key[0] == "c": dropped.append(C[0]); C = None
        else: dropped.append(ST.pop(key[1])[1])

    fixed = False; pr, st = build()
    if total_len(pr, st, clause_len) > cap:                  # the musts alone are too long: the model rewrites them shorter; a bad answer is ignored
        fixed = True; room = cap - (2 + len(st) if st else 0) - (2 + clause_len if clause_len else 0)
        if fix:
            try:
                new = fix(pr, room)
                if isinstance(new, str) and 0 < len(new.rstrip(". ")) <= room and all(p["label"] in new for p in P if p["label"]): pr = new
            except Exception:                                # noqa: BLE001  the model is optional: the word-boundary cut below still works
                pass
        if total_len(pr, st, clause_len) > cap:
            pr = cut(pr, room)                               # last resort: shorten at a word boundary
    return {"prompt": pr, "style": st, "dropped": dropped, "fixed": fixed, "length": total_len(pr, st, clause_len)}
