# Video generation on the 3090 box: optimization handoff (2026-11-16)

Purpose: everything learned while making ComfyUI video generation fast on the shared RTX 3090 box, written so a fresh session (or a future video agent) can continue without the chat history. It is about the engine and pipeline, not about any one video. The "episode" runs mentioned below were only the benchmark workload (a 60 s, 12-shot clip with narration).

Labels: **M** = measured on this box, **E** = estimated, **U** = untested idea. Nothing here is committed (RoyVa is not a git repo yet).

## 1. Constraints (read first)

- Box: `somdutta@somdutta-linux.local`, RTX 3090 24 GB (PCIe gen3 x8 under load, **M**), 45 GB RAM, models on a **SATA SSD (~500 MB/s)**, no NVMe seen. It also hosts a Home Assistant VM and is the owner's son's computer (online class, homework). Never reboot or restart the box, never start GPU work without the owner knowing. GPU is capped at 300 W by the owner (`sudo nvidia-smi -pl 300`, resets at reboot; `scripts/remote/install-boot-service.sh` exists but was never confirmed installed).
- ComfyUI runs in Docker as `comfyui-limited`: **24 GiB RAM cap, 8 CPUs, cpu-shares 256**, `--restart unless-stopped`. Data in `~/comfyui/data` on the box.
- **Claude cannot ssh** (managed policy denies `Bash(ssh:*)`, also nohup/systemctl/sudo). The owner runs short wrappers: `! bash ~/RoyVa/scripts/remote/<name>.sh`. **The `!` is mandatory**: a command pasted without it arrives as plain text and does nothing (happened many times). One command per message, no backticks, keep lines short (the terminal wraps long pastes).
- ComfyUI is reachable from this machine at `http://somdutta-linux.local:8188`. Everything else (Python clients, ffmpeg, Chatterbox TTS on CPU) runs here.

## 2. The locked default stack (**M**, best measured)

Launch: `! bash ~/RoyVa/scripts/remote/comfy-up-default.sh`
= image `comfyui-local:v0.42.1-cu130` (torch 2.10.0+cu130, built by `build-cu130-image.sh`), `--enable-dynamic-vram --disable-cuda-malloc --vram-headroom 2 --enable-triton-backend --use-ck-attention` (named "R4" in the notes). After every launch check `/system_stats` argv; env passthrough once silently failed.

Models (all INT8 ConvRot from the Winnougan repo, Apache-2.0, because the 3090 has no FP8 hardware): Wan 2.2 14B I2V high+low noise experts, `umt5_xxl_int8_convrot` text encoder, S2V INT8. 4-step lightx2v LoRAs v1 on both experts. Settings: **3 steps** (split 1 high / 2 low), **320x576** upscaled to 720x1280 with lanczos, 81 frames at 16 fps, cfg 1, shift 5, euler/simple. Step count and resolution are env-driven (`ROYVA_WAN_STEPS`, `W`, `H`).

Do not use `--highvram` as default: 4% faster (**M**, 284.7 vs 296.4 s on the batch) but it risks a GPU OOM (24 GB is already ~21.8 GB used during a batch) and ComfyUI dropped `--enable-dynamic-vram` from argv when it was set. Not tested with the speech model.

## 3. Measured results

Single clip, Wan 14B I2V, 384x688, 81 frames, 4 steps, warm (**M**):
FP8 plain 137 s -> FP8 + fp16 accumulation 120.5 s -> INT8 without Triton backend 168 s (slower: optimized backends were disabled) -> INT8 + Triton (cu128) 110.6 s -> INT8 + Triton (cu130) 107.6 s -> + "fast" flags bundle 107.4 s (no gain) -> **+ dynamic VRAM 83.0 s** (cold 116.4 s).

10 image-to-video clips, two-job batch (**M**):
| Config | Total | Job A | Job B |
|---|---|---|---|
| FP8 sequential, one clip at a time | 1,443 s | | |
| FP8 two-job | ~850 s (older run) | | |
| INT8 + cu130 + Triton, 384x688, 4 steps | 504 s | 264.9 | 229.5 |
| + dynamic VRAM | 423.5 s | 185.8 | 229.3 |
| + 3 steps + 320x576 (R2, Sage) | 296.4 s | 131.3 | 162.0 |
| R3 = R2 + `--highvram` | 284.7 s | 118.6 | 162.4 |
| **R4 = CK attention, no highvram (locked)** | **274.5 s** (288.9 s in the full run) | 113.8 | 156.3 |

Full pipeline from scratch (stills + voice in parallel, 10-clip batch, 2 speech clips, assembly), **M**: stills 63 s, voice done at 106 s, batch 289 s, speech clips 121 s, assembly 11 s = **527 s (8.8 min)** for 60 s of video. The original sequential FP8 pipeline took about 29.6 min (animation alone 27.6 min). Caveats: model files were warm in the page cache, 5 of 12 stills were reused.

Other measured facts:
- Two-clip batches cost ~55 s per clip, ten-clip batches 27-29 s per clip: setup is amortized.
- LoRA v1 vs the newer lightx2v 1022 rank-64 pair: identical speed (110.4 s vs 110.4 s, 2 clips, fresh seeds), no clear quality win. Staying on v1.
- LTX-2 19B distilled (fp8 file, text to video with generated audio, 512x768, 121 frames): loaded without OOM under dynamic VRAM, cold 126.5 s, warm 64.7 s, different 2D look, no image conditioning in the workflow. Not competitive with Wan batching; an image-to-video LTX workflow is untested.
- PCIe under load: gen3 x8, GPU util 100% during a batch.

## 4. Levers evaluated

Worked: INT8 ConvRot models (needs cu130 + Triton backend to pay off); cu130 torch (enables comfy-kitchen cuda/triton backends, which are disabled below cu13); **dynamic VRAM** (the ComfyUI default, which our old launcher disabled; halves step time on a single warm clip); two-job batching (each 14.5 GB expert loads once instead of once per clip; saved latents are bit-identical to sequential); 3 steps + 320x576 (visually fine on single clips; **M** speed, quality judged by eye); CK attention over Sage 2 (~7%); parallel ffmpeg assembly (59 s -> 11 s); running CPU voice in parallel with GPU stills.

No gain: `--fast` bundle (fp16 accumulation, cublas_ops, autotune; fp8_matrix_mult is a no-op on a 3090), torch.compile, EasyCache (a "14%" gain was a cold-vs-warm artifact), newer LoRA, `--highvram` (only 4%).

Dead ends and traps:
- FP8 weights with the Triton backend fail (`type fp8e4nv not supported`) on a 3090. INT8 only.
- Low-noise-only I2V gives broken output.
- A negative prompt needs cfg > 1, which doubles each step and breaks the 4-step LoRA (trained for cfg 1). Put "no extra people" in the positive prompt instead.
- Forced in-graph grouping of shots does not work: ComfyUI runs one output branch fully before the next and ignores node-id order. Grouping needs real data dependencies (zero latents), and the single-job version hit memory kills at 10 shots. The two-job version (job A saves latents with `SaveLatent`, they are re-uploaded to the input folder, job B uses `LoadLatent`) replaced it.

## 5. Memory and stability lessons

- ComfyUI's RAM-pressure cache is sized from whole-host RAM, not the container cap, so the 24 GiB cgroup OOM-kills it. This happened three times (LTX-2 load, a pipeline start, right after `/free`). **Never call `/free` between jobs** (unloading copies models into RAM and triggers the kill). Dynamic VRAM plus the restart policy made it survivable; LTX-2 now loads.
- Sage attention on a 3090 auto-dispatches to the Triton path, which needs gcc and a writable Triton cache; it fell back silently once. Look for the log line "Using sage attention" or equivalent.
- Dynamic VRAM has open upstream issues about LoRAs being dropped or rounded (#17690, #17704). Check quality when changing anything: sharp finished frames mean the LoRA is applied. PSNR against a baseline clip is 21-35 dB between runs even with identical settings (chaotic divergence), so use it only to catch collapses, not to rank.
- The box rebooted once at ~13:25 on 2026-11-15, cause unknown (suspected GPU power trip, hence the 300 W cap).

## 6. The unexplained cost: per-call overhead (best lead for further speed)

**RESOLVED 2026-11-16 by the timing probes (section 12): this was misattributed. There is no ~19 s per-call overhead in the locked stack.** Measured on a 10-clip job B (low expert, 2 steps per call, cold page cache after a restart): the FIRST sampler call took 47.2 s (first step 40.1 s, `cudaHostRegister` 3.38 s for 847 chunks / 14.8 GB, load() 0.15 s); every later call took 14.2 s (+-0.05) with load()+prepare 0.35 s and pin registration ~0. So the cost is one-time per expert load (weights streamed from the SATA SSD, ~33 s extra), plus ordinary GPU compute (~14 s per 2-step call, about 6-7 s per step) afterwards. The text below is the earlier, wrong reading; keep it only for the record.

Profiling with the websocket client (`runtime/episodes/lib/comfy_profile.py`) shows each `KSamplerAdvanced` call takes ~23.5 s for 2 steps, but only ~4.5 s of that is the second denoise step: **~19 s passes before the first step of every sampler call**, in both jobs, with or without the LoRA node (**M**), with decode/encode taken out between samplers (**M**), and with conditioning cached (**M**). The container log prints, for every call: `Model WAN21 prepared for dynamic VRAM loading. 13630MB Staged. 400 patches attached` (and WanTEModel/WanVAE lines). GPU util reads 100% during it; PCIe is not the limit. Roughly 190 s of the 424 s batch (before the 3-step change) is this overhead. Caveat: the profiled runs were slower than the real batch (job B 340-390 s profiled vs 229 s real), so treat per-call attribution as approximate.

Hypotheses (all **U**): per-call re-preparation/staging of the whole INT8 model (13.6 GB) and re-attachment of 400 patches; first-step kernel autotune/Triton compile per call; weights re-streamed from RAM each call under dynamic VRAM. How to find out: nsight/torch profiler on one KSampler call, ComfyUI `--verbose`, timing `load_models_gpu`, test the same call twice in one prompt.

## 7. Ideas for deeper optimization (including our own ComfyUI/runtime)

All **U** unless stated. Roughly ordered by expected value.
1. **Custom batching node**: one node that holds the model once and loops over N (conditioning, latent) pairs, so patching/staging happens once per expert instead of once per shot. Attacks the ~19 s/call overhead directly (potential ~100-190 s on 10 clips). Needs the ModelPatcher to stay loaded across items.
2. **Persistent worker instead of per-prompt graphs**: a small Python service (or custom ComfyUI node pack) that keeps hi and lo experts resident in RAM as prepared INT8 tensors and runs sampler loops directly, bypassing per-call prepare.
3. **Other inference stacks**: LightX2V has its own inference engine (quantization, offload, step distillation, the same LoRAs); also diffusers/Wan reference code with INT8 + block offload. Worth reading before writing our own. Not evaluated.
4. **Faster disk**: NVMe or RAM-resident models. A cold episode reads ~60 GB (FLUX, text encoder, two Wan experts, speech model): ~2 min on SATA vs ~20 s on NVMe (**E**, best case); near zero gain when the page cache is warm. A read-only M.2 slot check on the box was offered but never written. Raising the container RAM cap above 24 GiB could let both experts stay cached, but it risks the son's workload and the OOM path.
5. **Cache the text conditioning** across jobs and runs (umt5 encode is ~2 s per prompt plus a 6.4 GB model); run the text encoder on CPU or precompute.
6. **Cheaper decode/save**: VAEDecode is ~5 s per 81-frame clip and SaveVideo ~1.2 s; tiled/INT8 VAE, decoding at lower res then upscaling on a different engine, hardware encode.
7. **Fewer or cheaper frames**: shorter clips, reuse stills with pan/zoom for non-action shots, fewer animated shots (also a content decision). The owner dropped plain fps lowering.
8. **Alternative LoRAs/models**: a community 2-step LoRA pair claims ~2.4x faster with quality loss (unverified); LTX-2 I2V workflow (never run); Hunyuan 1.5 4-step path exists but unverified here; Wan 5B TI2V is smaller but looked worse.
9. **GPU**: raise the 300 W cap carefully (owner's call; earlier 300 W vs 350 W looked roughly equal), CUDA graphs, FP16 accumulation already tried.
10. **Second box**: a 3060 machine was considered and rejected for the pipeline split ("not worth it").

## 8. Code map (all under `~/RoyVa`)

- `mcp/image/comfy_client.py`: workflow builders: `wan14_i2v_workflow` (single clip), `wan14_i2v_hi_workflow` / `wan14_i2v_lo_workflow` (two-job batch; `_wan14_common` reads `ROYVA_WAN_STEPS`, `ROYVA_WAN_LORA_SET=1022`, `ROYVA_COMFYUI_WAN14_HI/LO`, `ROYVA_COMFYUI_WAN_CLIP`), `wan14_i2v_batch_workflow` (single-job grouping, superseded), `wan_s2v_workflow` (`ROYVA_COMFYUI_S2V`), `flux2_edit_workflow` (FLUX.2 klein reference edit for a consistent character), `ltx2_workflow`, `hunyuan_workflow`, `wan_workflow` (5B), `upload_image` (also used for wav and latent files), `run`, `run_multi` (all outputs plus saved latents), `free`.
- `runtime/episodes/lib/comfy_profile.py`: per-node and per-step timing over `/ws`.
- `runtime/episodes/newton60_e2e/`: the end-to-end template: `run_episode.sh` (timed stages), `stills.py`, `voice.py` (Chatterbox on CPU), `batch_two_job.py` (env `CLIP_PREFIX`, `W`, `H`, `SEED_OFF`, shot-number args), `animate.py` (speech-to-video and single clips), `assemble.py` (parallel ffmpeg: minterpolate to 24 fps, lanczos to 720x1280, loudnorm, `atempo` max 1.15, optional `CAPTIONS=1`, `CLIP_PREFIX`, `OUT`), `scenes.json` (shot list: kind i2v/s2v, still source, motion prompt, narration), `lora_timing.sh`, `ltx_test.py`. `runtime/episodes/newton60/` holds all earlier experiment scripts (`profile_*.py`, `exp_*.py`, `flags_test.sh`, `bench.py` in `newton1`) and their `timing.jsonl` logs.
- `assets/presenters/physics-teacher/` (reference image + `presenter.json`): the reusable character; stills come from FLUX klein 4B edit with the reference.
- `scripts/remote/`: `comfy-up-default.sh` (locked), `comfy-up-r2/r3/r4.sh`, `comfy-ctl.sh` (runs on the box; switches `COMFY_IMAGE`, `COMFY_SAGE`, `COMFY_FAST`, `COMFY_EXTRA`, `COMFY_DYNAMIC`, `COMFY_ENV`, `COMFY_RESTART`, `COMFY_MEM`, `COMFY_CPUS`), `fetch-wan.sh` (8-connection parallel downloader; sets `int8`, `int8te`, `int8s2v`, `loras`, `loras1022`, `flux2`, `ltx2`, ...), `build-cu130-image.sh`, `verify.sh` (read-only checklist), `comfy-logs.sh [pattern]`, `pcie.sh`, `oom.sh`, `disk.sh`, `cuda.sh`, `vm.sh`, `vm-balloon.sh`.
- Telegram helpers: `scripts/notify.sh "text"` (text; `NOTIFY_PREFIX=""` for copy-paste commands), the scratchpad `send_*.mjs` scripts for photos/videos (flood control returns 429 with `retry_after`, so space sends out), `scripts/claude-inbox-watch.sh` under Monitor for incoming replies (30 min expiry, re-arm).

## 9. Quality findings (workload-independent)

- Consistent character: FLUX.2 klein 4B reference edit works; Chatterbox (MIT) voice is acceptable, Kokoro sounded robotic.
- Wan 14B I2V with 3 steps at 320x576: scenes and motion coherent; crowd scenes (many faces) drift and re-invent faces between frames; an unrelated extra person can appear if the still already contains one (a still problem, fix the still). Mitigations to test (**U**): positive-prompt constraints, 4 steps for hard shots, re-roll seeds and auto-pick, simpler compositions.
- CK vs Sage attention clips look equivalent by eye; v1 vs 1022 LoRA likewise.

## 10. Licences (verify before reuse)

Apache-2.0 / MIT seen: Wan 2.2, FLUX.2 klein 4B, Chatterbox (MIT), Kokoro (Apache-2.0), INT8 ConvRot repo (Apache-2.0). Not verified: LTX-2 (community licence), Hunyuan 1.5, lightx2v LoRAs, the INT8 text encoder, wav2vec2. Hold: HunyuanVideo H3 (licence). The owner wants modular, license-aware parts reusable for other work.

## 11. Open items

- Decide next speed step: per-call overhead investigation (section 6) and/or custom batching node (7.1) vs NVMe vs fewer animated shots.
- Quality: regenerate stills that already contain unwanted people; test 4 steps on crowd shots.
- Install the 300 W boot service if the owner confirms; consider deleting unused FP8/INT8-tensor model files if disk is needed (287 GB free of 916 GB).
- Scheduled-agents runner/price-watcher, PWA, optional Siri endpoint, Ford automation live edit run, Qwen3.5-122B-A10B evaluation, commit the uncommitted work, license inventory, the video agent itself (job queue + status endpoint + Telegram `/agents`).
- Owner preferences: short replies; label measured vs estimated; do the research proactively instead of waiting for the owner to find options; no captions; one command per message with `!`; talk on Telegram when the owner steps away.

## 12. ComfyUI code audit and probes (2026-11-16, read from source v0.42.1, nothing measured yet)

- Source cloned for reading only (scratchpad, public tag). Findings: `ModelPatcherDynamic.load()` (model_patcher.py ~1878) has no early exit and re-runs the full prepare on every sampler call (module walk, 400 `LowVramPatch` objects); LoRA is applied per weight per forward via `LowVramPatch`. Best candidate for the ~19 s: `cudaHostRegister` of ~13.6 GB pinned memory (pinned_memory.py), re-done if pins are released between calls (`unregister_inactive_pins`, `partially_unload_ram`, `ensure_pin_budget` under RAM pressure). **U**. Stripping `comfy_api_nodes`/tests/`comfy_extras` (~8 MB of Python) cannot speed up sampling; `comfy_aimdo` 0.5.6 (native, dynamic VRAM) is not auditable from source.
- Experiment A: `! bash ~/RoyVa/scripts/remote/comfy-up-nopin.sh` = locked stack + `--disable-pinned-memory`. Run the 10-clip two-job batch and compare to 274-289 s.
- Experiment B: `! bash ~/RoyVa/scripts/remote/comfy-up-instrument.sh` mounts timing probes (`runtime/comfy-instrument/`, patch in `perf-probes.patch`, checksums verified against the image first). Read with `! bash ~/RoyVa/scripts/remote/comfy-perf.sh`. Logs per sampler call: `load_models_gpu`, load() phases, `cudaHostRegister` seconds/MB, pin evictions, time to each step.
- Go back to normal: `! bash ~/RoyVa/scripts/remote/comfy-up-default.sh`. `comfy-ctl.sh` gained `COMFY_MOUNTS` (extra bind mounts), forwarded by `comfy-up.sh`.

### 12b. Results (2026-11-16, locked INT8 stack, measured)

- **Correction:** the first three runs of the day (386, 335, 386 s) accidentally used FP8 models because `batch_two_job.py` was launched without the INT8 env vars that `run_episode.sh` exports (defaults are FP8). Always take the env from `run_episode.sh`. Ignore the FP8 numbers (14.2 s per 2-step call etc.).
- Locked default, 10 shots: **289.4 s (job A 128.0, job B 156.5)**, same as the earlier reference. The timing probes cost no measurable time (FP8 default 386 s vs FP8 probes 386 s).
- Framework overhead per sampler call: load()+prepare 0.15-0.20 s, pin registration ~0 after the first call (**M**). The old "19 s per call" lead (section 6) is closed. Experiment A (`--disable-pinned-memory`) and the custom batching node are dropped.
- GPU sampling (1 s, `scripts/remote/gpu-sample.sh`, 282 s window, **M**): SM >=95% in 141 s (50%), <50% in 129 s (46%). Idle stretches ~60 s at the start of job A and ~55 s at the start of job B, with PCIe-in ~300 MB/s: the SATA SSD reading each 14.5 GB expert (**E**). During compute: SM 86-89%, ~280 W, power-limit flag on ~95% of the busiest seconds, SM clock median 1485 MHz vs 1980 max, no thermal throttling, PCIe-in median 16 MB/s (no per-step streaming).
- **Next levers, by size:** (1) expert load time: NVMe, or keep both experts in RAM cache (container cap is 24 GiB, owner's decision) -> up to ~110 s of a 289 s batch (**E**); (2) the 300 W cap during compute (owner's call; was judged roughly equal at 350 W earlier); (3) VAE decode/save and the job A -> job B hand-off.
- Probe tooling stays available: `comfy-up-instrument.sh`, `comfy-perf.sh`, `gpu-sample.sh` (note: two samplers running at once write the same log).

### 12c. Timeline breakdown and what was ruled out (2026-11-16, INT8 locked stack, measured from docker timestamps)

- 10-clip batch = ~275-289 s: sampling compute ~109 s (A: 1 step x 10 at ~3.9 s; B: 2 steps x 10 at ~7.0 s, i.e. ~3.5 s per INT8 step), per-clip VAE encode in job A (~2.3 s x 10) and VAE decode + save in job B (~4.4 s x 10) ~72 s, one-time loads ~80 s (T5 first load+encode 16.5 s, hi expert first sampler call ~27-31 s extra, lo expert ~37 s extra), uploads/hand-off ~8 s.
- The 289 s result was NOT a warm-cache result: model files are at ~0-1% in the page cache after every batch (container pins ~14.8 GB per expert; box has ~17.5 GB used elsewhere). Pre-caching the hi expert from the host (`cache-warm.sh hi`, 29 s at ~470 MB/s, 100% cached) saved only 12.9 s on job A (275.2 s total), so disk explains only ~10-13 s of each ~30-37 s expert first-call cost; the rest (~25 s) is unexplained (candidates: pin registration 3.4 s, page faults/copy, first-use kernel setup). NVMe would save at most ~26 s per batch (**E**).
- Ruled out: per-call load/prepare overhead (0.35 s), pinned memory, `--fast autotune` (cudnn.benchmark: 287.3 vs 289.4 s, no VAE gain), VAE dtype (Wan 2.1 VAE already bf16 per sd.py). Attention is already INT8 (`--use-ck-attention` -> `comfy_kitchen.int8_attention`).
- Still open: the ~25 s per-expert first-call cost, the serial per-clip VAE work (ComfyUI runs one node at a time; overlapping decode/save with sampling would need decoding outside the executor, VRAM is tight at ~21.8 GB), T5 embedding cache (16.5 s), kernel profile (torch.profiler on one warm call), the 300 W power cap during compute.
- Scripts added: `comfy-up-autotune.sh`, `comfy-timeline.sh`, `cache-check.sh`, `cache-warm.sh`, `gpu-sample.sh`.

### 12d. Parallelised pipeline (2026-11-16, implemented, NOT yet run end to end)

`runtime/episodes/newton60_e2e/run_episode.sh` now overlaps CPU work (this machine) with GPU work (the box); GPU order is unchanged (stills -> 10-clip batch -> speech clips), no `/free` calls. Old serial script: `run_episode_serial.sh`; baseline: `timing_e2e_baseline_527s.txt` (527 s). New timings go to `timing_e2e_par.txt`.
- Batch starts right after the stills (it only needs the stills); voice runs in the background and must be finished before the speech clips (they need say1/say12.wav) and assembly. Expected saving ~43 s (**E**: batch was waiting for the 106 s voice while stills took 63 s).
- The 10 image-to-video segments are assembled here while the speech clips run on the box; afterwards only segments 1 and 12 plus the concat remain (expected ~6-9 s saved, **E**). `assemble.py` takes optional shot numbers, skips segments newer than their clip/wav/scenes.json, runs all segments at once (scratch test: 5.7 s vs ~11 s, rerun 0.2 s).
- `batch_two_job.py` uploads stills and latents in parallel (a few seconds, **E**); `stills.py` now exits nonzero on a failed still; every stage's exit status is checked.
- Control flow tested with stubs only (ordering and failure gating). Timing test must use a fresh prefix, because `animate.py` skips existing clip files: `CLIP_PREFIX=par OUT=episode_par.mp4 bash run_episode.sh`. Compare marks, not just the total (the batch alone varies 275-289 s with cache state); the real voice time is `voice_total` in `voice.log`.
- Not implemented: moving SaveVideo's h264 encode off the box (unmeasured, ~1.2 s per clip), multi-process voice (already hidden behind the batch), cross-episode pipelining (belongs in the video agent's job queue: next episode's voice and stills prep while the current episode's speech clips run).

### 12e. First end-to-end run of the parallelised pipeline (2026-11-16 12:27, measured)

`CLIP_PREFIX=par OUT=episode_par.mp4 bash run_episode.sh` on a freshly restarted default stack (cold start): **472 s (7.9 min) vs 527 s baseline, -55 s (-10%)**. Output equivalent (720x1280, 24 fps, h264+aac, 60.267 s, same size class), no stage errors.
- Stills 64 s (63). **Batch started at 64 s (was 106 s): -42 s.** Voice finished at 113 s on its own clock (`voice_total` 108.6 s), hidden behind the batch. Batch 285.6 s (A 127.0, B 156.2; was ~289). Speech clips 120 s (was 121). After the speech clips only 3 s remain (was 11 s: -8 s; the 10 image-to-video segments were assembled during the speech clips).
- New finding: speech-clip stage is dominated by a one-time load: shot 1 took 93 s, shot 12 took 26 s, so ~67 s of the 120 s is the first-use cost of the 17.3 GB S2V model (cold read alone would be ~37 s at ~470 MB/s, **E**).
- Critical path now: stills 64 + batch 285 + speech clips 120 + final 3 = 472 s. Remaining levers: one-time model loads (batch ~80 s, S2V ~67 s), per-clip VAE (~72 s), sampling compute (~109 s batch), text encoder first load (16.5 s). Target 300 s still needs sampling/loads cut or fewer animated shots.

### 12f. Kernel profiling build (2026-11-16, built and unit-tested locally, not yet run on the box)

`comfy-up-instrument.sh` now also profiles ONE warm call each of: high-expert sampler (#3), low-expert sampler (#13), VAE encode (#3), VAE decode (#3), with torch.profiler CUDA-only (no CPU buffers: host RAM is tight, the container has OOM-died at 24 GiB before). Output: `perf_profile_<kind>_<n>.txt` in ComfyUI's output folder (kernel-bucket table, top-25 kernels, stock `key_averages` table as fallback); fetch with `GET /view?filename=perf_profile_sampler_3.txt&type=output`. A capture with no kernels is reported as FAILED (CUPTI missing/blocked).
- Call numbers are per process: restart with the instrument launcher, then run ONLY `batch_two_job.py` (INT8 env exported, `CLIP_PREFIX=prof RUN_NOTE=profiled`), no other prompt first. Do not use the timing from that run as a benchmark (profiler overhead; `RUN_NOTE` marks it in `timing.jsonl`). ~5 min GPU. Afterwards restore `comfy-up-default.sh`.
- Headroom check to apply to the result (estimates, **E**): a step is ~4.2e14 INT8 linear ops + ~1.9e14 attention ops at ~15k tokens; at the measured 3.5-3.9 s per step that is ~155-175 TOPS, against a 3090 dense INT8 peak of ~284 TOPS (~250 at the power-capped ~1485 MHz): the stack may already be near ~65% of peak, so a custom kernel may only win at the margins. Compute achieved TOPS per bucket (gemm, attention) from the profile before deciding; read the raw top-25 list, the bucket regexes are loose.

### 12g. Kernel profile results (2026-11-16, measured with torch.profiler CUDA-only; raw files in `runtime/comfy-instrument/results/profile-2026-11-16/`)

Profiled run = INT8 locked stack, cold start, profiler overhead (batch 295.7 s, marked `profiled` in timing.jsonl; not a benchmark). Per DiT step, GPU kernel time: job A call (1 step) 3.55 s, job B call (2 steps) 6.88 s = 3.44 s/step; GPU busy 94% / 99.7% of the call wall time, so there are no idle bubbles inside sampling.
- Per step: INT8 GEMM (CUTLASS, `DefaultGemmWithVisitor`) ~1.55-1.60 s (44-47%); INT8 attention (`qk_int_sv_i8_attn_kernel`, QK and PV both INT8) ~1.15 s (33%); activation quantize (`quantize_int8_rowwise_convrot64`, `quant_v_int8`, `quant_qk_fused`) ~0.40 s (11%); norm 0.09, elementwise 0.1, adaln/rope 0.08, pinned HtoD weight copies 0.18 s (job A call only).
- Achieved vs peak (**E**, FLOPs from Wan 14B dims: 15,120 tokens, dim 5120, ffn 13824, 40 layers): INT8 GEMM 3.61e14 ops/step / 1.55 s = ~230 TOPS = roughly 80-95% of the 3090's INT8 dense peak (284 TOPS at 1695 MHz; ~250-270 at the power-capped clocks): essentially at the roofline. Self-attention 1.87e14 / 1.06 s = ~176 TOPS = roughly 62-70% of peak (typical for a good attention kernel). No LoRA kernels appear in the step: the lightx2v LoRA is applied when weights are staged (part of the first-call cost), not per step.
- VAE (bf16 cuDNN conv3d): encode 2.0 s/clip (conv 75%, elementwise 22%, NCHW<->NHWC layout conversions ~8%), decode 3.4 s/clip (conv 75%, elementwise 22% in 7,887 tiny launches, layout conversions ~9%).
- Realistic kernel upside (**E**, needs real CUDA work): fuse norm/adaln with quantize (~0.1-0.25 s/step), a better attention kernel (<=0.2-0.3 s/step), VAE elementwise fusion + channels_last_3d (~0.4-0.7 s per clip). Total ~20-30 s of a 472 s episode (4-6%). Kernels are not the big lever; model loads (~150 s) and the compute floor (steps, resolution, number of animated shots, the 300 W cap) are.

### 12h. Full-episode kernel profile and the first-call stall (2026-11-16, measured; profiled run 501 s, not a benchmark; raw files in `runtime/comfy-instrument/results/profile-2026-11-16-full-episode/`)

**CORRECTION to 12c/12e:** I earlier concluded disk explained only ~10-13 s of each expert's first-call cost. The profile of each model's FIRST sampler call (wall minus GPU kernel time = time the GPU sat idle inside the call) says otherwise:
| Model | file | cold read at 467 MB/s (measured SATA speed) | first-call stall (wall - GPU) |
|---|---|---|---|
| FLUX klein fp8 | 3.79 GB | 8.1 s | 8.1 s (11.3 wall, 3.2 GPU) |
| Wan high | 13.54 GB | 29.0 s | 35.3 s (41.4 wall, 6.0 GPU) |
| Wan low | 13.54 GB | 29.0 s | 35.2 s (44.7 wall, 9.4 GPU) |
| Wan S2V | 17.27 GB | 37.0 s | 39.4 s (58.4 wall, 18.9 GPU) |
The stall matches size / SATA speed within ~10-20% for all four (the extra on the Wan experts is ~3.4 s pin registration plus LoRA staging). First-call stalls total ~118 s; with the T5 (6.3 GB, ~13-16 s) and the FLUX text encoder, a cold episode reads ~70 GB = ~150 s at 467 MB/s, i.e. the ~150-180 s of "loads". So the loads are cold SATA reads (strongly supported, not yet confirmed with a direct disk-throughput measurement). The earlier host pre-cache test saved only 12.9 s probably because the page cache and the 14.8 GB pinned copy cannot coexist in the box's RAM (as pins grow, not-yet-read cache pages are evicted) (**E**, explains the number).
- Levers: NVMe (est. ~3 GB/s -> ~70 GB in ~25 s, saving ~100-130 s per episode, **E**); read less: S2V's workflow hardcodes the FP8 T5 (`umt5_xxl_fp8_e4m3fn_scaled`) instead of the INT8 T5 the batch just used (6.3 GB, ~13 s, **E**; generic fix: use `ROYVA_COMFYUI_WAN_CLIP` like the other workflows); dropping the speech-model stage would save its 17.3 GB + T5 + 120 s.
- Warm kernel facts: FLUX klein sampler 2.55 s/still, GPU 99% busy, bf16 GEMM 73% (FP8 weights are dequantized each step, only 0.05 s), INT8 attention 10%; FLUX VAE decode 0.27 s; rest of the 4.7 s per still is text encode, save, HTTP. Speech clip sampler: 4 steps, 15.9 s GPU of 18.5 s wall (86% busy), ~4.0 s/step vs 3.44 s/step for the batch (INT8 GEMM 1.58 s/step and attention 1.13 s/step identical to Wan I2V; extra: fp16 (unquantized) GEMMs 1.14 s/call, pinned->GPU weight copies 0.77 s/call, 6,400 tiny elementwise launches). Wan VAE decode 3.4-3.6 s per clip (speech and batch alike); Wan I2V image encode 2.2 s per clip vs 0.045 s for the speech clips' single-frame encode (I2V encodes a full 81-frame mostly-gray sequence; an exact shortcut would need the encoder's temporal receptive field checked).

### 12i. Storage facts of the 3090 box (2026-11-16, measured by `scripts/remote/storage-check.sh`, board spec from web reviews/manual)

- ASUS X99-A (LGA2011-v3), BIOS 1901. NO NVMe drive. Disks: Samsung 850 EVO 500GB x2, 850 EVO 1TB (`sdc`, root filesystem `/`, holds `~/comfyui/data/models`, 584 GB used / 286 GB free), USB Seagate Expansion 1TB. SATA links at 6 Gbps; measured model read speed 467 MB/s = the SATA ceiling.
- Per reviews/manual (2015 sources, **E** that nothing changed): the X99-A has ONE M.2 Socket 3 (M key, PCIe 3.0 x4 from CPU lanes, PCIe-only, no SATA M.2). It shares bandwidth with the black PCIEX16_4 slot (BIOS option "PCIEX16_4 Slot Bandwidth": Auto disables that slot when an M.2 device is detected; X8 mode keeps the slot with M.2 disabled). Unknown: what sits in PCIEX16_4, the CPU model (28 vs 40 lanes; the GPU measured gen3 x8 under load), and drive-size limits (2280 vs 22110).
- Installing a drive needs a power-off (the box also hosts a Home Assistant VM and the son's class machine): owner to schedule. A ~3 GB/s NVMe would cut ~70 GB of cold reads from ~150 s to ~25 s; expect ~100-120 s saved per episode after the unchanged ~10-15 s of pin registration/LoRA staging (**E**).

### 12j. SATA stripe for the model disk (2026-11-16, scripts written and unit-tested locally; NOT yet run on the box)

Audit (`stripe-audit.sh`): `sda3` (UUID 37435b5b-...) and `sdb2` (UUID 9633129b-...) are empty ext4 (28 KB used, only lost+found), idle since boot, no open files, no container/VM references; VMs (`pluto-vm`, `Haos`) run under libvirt and have nothing open there. Models are 231 GB (142 diffusion, 39 checkpoints, 38 text encoders) on `sdc`, which also holds the OS and the VMs' disks (**E**). Expected: ~2x sequential read, first-call stalls ~118 s -> ~60 s, ~55-75 s saved per episode (**E**); ComfyUI's small mmap reads might not reach 2x, so verify.
- Scripts (`scripts/remote/`): `stripe-push.sh` (copies the setup script to the box), `stripe-setup-remote.sh` (runs on the box as root: dry run by default, `--apply` + typed confirmation; refuses unless both partitions carry the audited UUIDs, are plain ext4, empty, unused, SMART-passed; RAID0 chunk 64K, ext4 stripe-aware, read-ahead 4 MB; COPIES the models (rate-limited to 200 MB/s, source stays on `sdc`); changes /etc/fstab (backup kept), /etc/mdadm/mdadm.conf, a udev read-ahead rule; fstab line has `nofail,x-systemd.before=docker.service` so a reboot cannot start ComfyUI on an empty models folder), `comfy-up-stripe.sh` (refuses unless /mnt/models is mounted with the model files; mounts it read-only over /data/models), `disk-sample.sh` (per-disk read counters once a second; run next to `gpu-sample.sh`).
- Install prerequisites WITHOUT recommends (mdadm otherwise recommends a mail server): `sudo apt install --no-install-recommends mdadm smartmontools rsync psmisc`. The setup must run in a real terminal (sudo password): `ssh -t somdutta@somdutta-linux.local 'sudo bash ~/stripe-setup.sh'` (dry run), then `... --apply`.
- Success test = the cold first-call stalls (FLUX 8 s, experts 35 s, speech 39 s at SATA speed) in a full-episode profile run, plus `disk-sample.sh` showing sda and sdb both reading; the `dd` figure printed by the setup is only a first look. Rollback: remove the mount from the launcher (`comfy-up-default.sh`), then umount/stop md0 per the header of `stripe-setup-remote.sh`. If the stripe is not mounted after a reboot, do not run ComfyUI from it.

### 12k. Speech workflow now shares the episode's text encoder (2026-11-16, code change, not yet run on the GPU)

`wan_s2v_workflow` (comfy_client.py) hardcoded the FP8 T5 (`umt5_xxl_fp8_e4m3fn_scaled`); it now reads `ROYVA_COMFYUI_WAN_CLIP` like the other Wan workflows, and `run_episode.sh` already exports the INT8 file. Expected: the speech stage no longer cold-loads a second 6.3 GB T5 (~13 s, **E**; whether the INT8 T5 is still resident after job B depends on RAM pressure). Quality check pending: the speech clips' text encoder changes from FP8 to INT8 (the batch has used the INT8 T5 all along). Other pieces have NO INT8 file on the box and were left alone: FLUX klein (fp8), Qwen3-4B text encoder (bf16), both VAEs, wav2vec2 (fp16), the lightx2v LoRAs. Defaults in the workflow builders still fall back to FP8 names when the env is not set (the trap behind the early 386 s runs); flip them only if INT8 files are guaranteed wherever this runs.

### 12l. Stripe verified (2026-11-16, measured by `stripe-verify.sh`)

`stripe-setup` ran to completion (array, ext4, fstab line, udev read-ahead, 34 files / 247 GB copied with identical sizes; its own speed test crashed on `dd iflag=direct`, which is cosmetic). State confirmed: `md0` active raid0 on sda3+sdb2 (64K chunks), mounted at /mnt/models with `stripe=32`, fstab has `nofail,x-systemd.before=docker.service`, old lines gone, `mdadm.conf` ARRAY line present, read-ahead 4096 KB. Cold read of the 13.5 GB high expert: old disk 536 MB/s sequential / 524 MB/s mmap page-touch; stripe 1090 / 1042 MB/s = 2.0x in both patterns. The old disk reads 536 MB/s sequentially (not 467), so disk is ~70-85% of each first-call stall (FLUX 7 s, experts 25 s, speech 32 s of pure disk time vs stalls of 8/35/35/39 s); the remaining 1-10 s per model is pin registration/staging. Expected after the stripe: stalls ~118 s -> ~70 s, ~50-55 s saved per episode (**E**).
- Fair test: `cache-evict.sh` (drops cached model pages after the copy), `comfy-up-stripe.sh`, then a full episode with a fresh `CLIP_PREFIX` plus `gpu-sample.sh` and `disk-sample.sh`; compare stage marks with `timing_e2e_par_run1_472s.txt` (stills 64, batch 285, speech 120, total 472). Note the run1 numbers were cold-start. Pending: optional `sudo systemctl daemon-reload` (owner).

### 12m. Episode from the stripe (2026-11-16 14:27, measured; cold start, page cache evicted first; default flags, no probes): 391 s vs 472 s (-81 s, -17%)

`CLIP_PREFIX=stripe1 OUT=episode_stripe1.mp4 bash run_episode.sh` after `comfy-up-stripe.sh` (container verified: /data/models is /dev/md0, no extra search paths, no symlinks) and `cache-evict.sh`. Stage marks (timing in `timing_e2e_par.txt`; previous runs kept as `timing_e2e_par_run1_472s.txt` and `..._run2_profiled_501s.txt`): stills 53 s (was 64; first still 24.4 s vs 35.3), batch 248.4 s (A 104.4, B 140.8; was 285.6 / 127.0 / 156.2), speech clips 87 s (shot 1 58.6 s, shot 12 27.7 s; was 93 / 26), final assembly 3 s. Output identical in format (720x1280, 60.267 s), no stage errors. Disk (`disk-sample.sh`): 77.7 GB read from md0 (sda 38.8 + sdb 38.9 in parallel, peak 1057 MB/s), only 1.9 GB from the old disk.
- Two changes are mixed in the speech stage: the stripe and the speech workflow now using the INT8 text encoder (12k). Speech-clip quality with the INT8 text encoder still needs a visual check.
- Critical path now: stills 53 + batch 248 + speech 87 + final 3 = 391 s. Remaining cold reads ~78 s at ~1 GB/s; NVMe (~3 GB/s) would save ~50 s more (**E**). Compute floor (sampling ~109 s batch + ~52 s speech, VAE ~72 s) is unchanged. Reboot behaviour with the stripe (fstab `x-systemd.before=docker.service`) is untested; do not reboot just to test; fallback `comfy-up-default.sh`.

### 12n. Paris episode with a locally written script (2026-11-16, measured)

First episode whose narration, still prompts and motion prompts were written by the local Qwen3.6-35B-A3B (`mcp/video/script_writer.py`, prototype) with RoyVa web-checking the facts. Script stage (draft-first with a per-fact RoyVa check and rewrite rounds): 559 s, of which 509 s were 22 sequential web checks (typical 11-16 s; two "wrapped" checks of 81 s and 90 s hit RoyVa's step cap; rounds 2-3 re-checked reworded versions of the same facts and led to three paint-related shots). The script stage was longer than the render. RoyVa's gateway handles concurrent `/v1/ask` calls: 4 web checks ran in 34 s wall vs ~99 s one by one; unprivileged identity `pipeline:video` can use `web_lookup`. Voice speed measured 18.2 chars/s (not 15.5).
- Render (`CLIP_PREFIX=paris1`, stripe stack, cache not evicted): 408 s = stills 59, batch 256.2 (A 108.4, B 144.4), speech clips 89.2 (shot 1 56.8, shot 12 32.4), assembly 4. vs 391 s for the cold-evicted newton60 run: same within ~4%. Output 60.267 s, 720x1280, 27 MB.
- Lessons: a still with extra people (workers in a boat) keeps them in the clip; the scene text said "no other people" but also "workers", a contradiction the model produced; "holding X" props unrelated to the topic (heart, lace) come from letting the model pick a prop per fact. The writer was a prototype: a redesign (brief -> research with source-and-recheck -> storyboard -> prompt compiler -> validation gates) was proposed and awaits the owner's decisions.
