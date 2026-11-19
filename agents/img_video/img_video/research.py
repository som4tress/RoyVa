"""Research providers: a question goes in, text comes out. The agent calls this only for narration facts. Today's provider is RoyVa's gateway (read-only web_lookup);
a self-running agent would swap in another provider here without touching the rest. The agent identifies itself as an unlisted identity (no private scopes, attributable traces)."""
import json
import time
import urllib.error
import urllib.request


class ResearchError(RuntimeError):
    pass


def ask(cfg_research, question, timeout=300):
    """Returns {"text": answer, "provider": ..., "intents": [...], "secs": float}. Raises ResearchError if no real web lookup happened."""
    if cfg_research.get("provider") != "royva":
        raise ResearchError(f"unknown research provider '{cfg_research.get('provider')}'")
    headers = {"Content-Type": "application/json"}
    if cfg_research.get("token"): headers["Authorization"] = "Bearer " + cfg_research["token"]
    body = json.dumps({"text": question, "user": cfg_research["identity"]}).encode()
    req = urllib.request.Request(cfg_research["url"].rstrip("/") + "/v1/ask", data=body, headers=headers)
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ResearchError(f"RoyVa gateway refused the question (HTTP {e.code}): {e.read(300).decode('utf-8', 'replace')}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ResearchError(f"RoyVa gateway not reachable at {cfg_research['url']}: {e}")
    intents = d.get("routing", {}).get("intents", [])
    text = (d.get("answer") or "").strip()
    if "web_lookup" not in intents:
        raise ResearchError(f"the question was not routed to a web lookup (routed to {intents}); answer ignored")
    if len(text) < 20:
        raise ResearchError("RoyVa returned an empty or too short answer")
    return {"text": text, "provider": "royva", "intents": intents, "secs": time.time() - t}
