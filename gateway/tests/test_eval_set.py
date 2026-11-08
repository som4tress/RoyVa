import json
from pathlib import Path
from royva_gateway import registry

ROOT = Path(__file__).resolve().parent.parent
ITEMS = [json.loads(l) for l in (ROOT / "eval/eval_set.jsonl").read_text().splitlines()]
REG = registry.load(ROOT / "registry")
MODES = {"new", "continuation", "steer", "confirmation", "fallback"}


def test_labels_refer_to_real_intents():
    for it in ITEMS:
        for i in it["expected_intents"] + (it["prior"]["intents"] if it["prior"] else []):
            assert i in REG.intents, (it["id"], i)
        assert it["expected_mode"] in MODES


def test_ids_unique_and_categories_present():
    assert len({i["id"] for i in ITEMS}) == len(ITEMS)
    cats = {i["category"] for i in ITEMS}
    assert cats == {"standalone", "cross", "unrouted", "followup", "state"}


def test_every_intent_has_standalone_eval_items():
    for iid in REG.intents:
        assert any(i["category"] == "standalone" and iid in i["expected_intents"] for i in ITEMS), iid


def test_no_leakage_from_registry_phrases():
    train = set()
    for intent in REG.intents.values():
        train |= {s.lower() for s in intent.examples + intent.negatives + intent.continuations}
    leaks = [i["text"] for i in ITEMS if i["text"].lower() in train and i["category"] != "state"]
    assert not leaks, leaks


def test_state_items_carry_state():
    for i in ITEMS:
        if i["expected_mode"] == "confirmation":
            assert i["state"]["pending_confirmation"]
        if i["expected_mode"] == "steer":
            assert i["state"]["busy"]
