"""ComfyUI custom node with NO nodes: a READ-ONLY timing hook. It wraps a handful of ComfyUI internals with a stopwatch and writes one line per call to ComfyUI's own log
("[wan_timing_diag] ..."), so we can see where the ~2 s per sampler call goes in the Wan jobs (model re-prepare? detach of the previous clone? cleanup? memory freeing?). It changes NO behaviour:
every wrapper calls the original with the same arguments, returns its result and re-raises its exceptions unchanged; any failure of the stopwatch itself is swallowed.
The wrappers add a torch.cuda.synchronize() before and after each timed call so GPU work is attributed to the call that caused it (this makes the measured run slightly slower, not different).
Switch it off without a restart: create the file /data/wan_diag.off on the box (~/comfyui/data/wan_diag.off); remove the file to switch it on again. Remove it entirely by deleting
~/comfyui/data/custom_nodes/wan_timing_diag.py and restarting ComfyUI. Install: scripts/remote/wan-diag.sh. Read: scripts/remote/wan-diag-read.sh."""
import functools
import importlib
import logging
import os
import threading
import time

OFF_FILE = os.environ.get("WAN_DIAG_OFF_FILE", "/data/wan_diag.off")
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
_depth = threading.local()
T0 = time.time()

# (module path, class name or None, attribute): what to time. Names that do not exist in this ComfyUI version are skipped (and listed in the "installed" line).
TARGETS = [
    ("comfy.sample", None, "sample"),                                   # one whole sampler call: prepare + steps + finish
    ("comfy.sampler_helpers", None, "prepare_sampling"),
    ("comfy.sampler_helpers", None, "cleanup_models"),
    ("comfy.model_management", None, "load_models_gpu"),
    ("comfy.model_management", None, "free_memory"),
    ("comfy.model_management", None, "cleanup_models_gc"),
    ("comfy.model_patcher", "ModelPatcher", "detach"),                  # a previous clone being detached when a new clone loads
    ("comfy.model_patcher", "ModelPatcher", "cleanup"),
    ("comfy.model_patcher", "ModelPatcher", "pre_run"),
    ("comfy.model_patcher", "ModelPatcherDynamic", "load"),             # the "prepared for dynamic VRAM loading ... patches attached" step
    ("comfy.model_patcher", "ModelPatcherDynamic", "partially_unload"),
    ("comfy.model_patcher", "ModelPatcherDynamic", "unpatch_hooks"),
]


def _on(): return not os.path.exists(OFF_FILE)


def _sync():
    try:
        import torch
        if torch.cuda.is_available(): torch.cuda.synchronize()
    except Exception:                                                    # noqa: BLE001
        pass


def timed(name, fn):
    """Return fn wrapped with a stopwatch. Behaviour-neutral: same args, same result, same exceptions."""
    if getattr(fn, "_wan_diag", False): return fn

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try: on = _on()
        except Exception: on = False                                     # noqa: BLE001
        if not on: return fn(*a, **kw)
        try:
            d = getattr(_depth, "n", 0); _depth.n = d + 1; _sync(); t = time.time()
        except Exception: return fn(*a, **kw)                            # noqa: BLE001
        try:
            return fn(*a, **kw)
        finally:
            try:
                _sync(); dt = time.time() - t; _depth.n = d
                logging.info("[wan_timing_diag] %s%-34s %7.3fs   (t+%.2fs)", "  " * d, name, dt, time.time() - T0)
            except Exception: pass                                       # noqa: BLE001
    wrapper._wan_diag = True
    return wrapper


def install(targets=TARGETS, loader=importlib.import_module):
    done, skipped = [], []
    for mod_path, cls_name, attr in targets:
        label = f"{cls_name + '.' if cls_name else ''}{attr}"
        try:
            owner = loader(mod_path)
            if cls_name: owner = getattr(owner, cls_name)
            fn = owner.__dict__[attr] if cls_name else getattr(owner, attr)       # a method defined on THIS class, not an inherited one
            setattr(owner, attr, timed(label, fn)); done.append(label)
        except Exception as e:                                           # noqa: BLE001
            skipped.append(f"{label} ({type(e).__name__})")
    logging.info("[wan_timing_diag] installed: %s | skipped: %s | off-switch file: %s", ", ".join(done) or "none", ", ".join(skipped) or "none", OFF_FILE)
    return done, skipped


try:
    install()
except Exception as e:                                                   # noqa: BLE001  never stop ComfyUI from starting
    logging.warning("[wan_timing_diag] not installed: %s", e)
