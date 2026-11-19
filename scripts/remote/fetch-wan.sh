#!/usr/bin/env bash
# Runs ON the 3090 box. Downloads Wan 2.2 files into the ComfyUI models folder. Resumable, skips files already there.
# Usage: bash -s 5b   (default)   |   bash -s 14b-i2v hunyuan   (sets run in order; a failed file prints an error and the next one continues)
M="${COMFY_MODELS:-$HOME/comfyui/data/models}"
R=https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files
W21=https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files
pget() {  # url outfile : 8 parallel range requests (one connection from the CDN is slow)
  python3 - "$1" "$2" <<'PY'
import sys, urllib.request, threading, os, time
url, out = sys.argv[1], sys.argv[2]
N = 8
req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
with urllib.request.urlopen(req) as r:
    final = r.geturl(); total = int(r.headers["Content-Range"].split("/")[1])
with open(out, "wb") as f: f.truncate(total)
done = [0]; lock = threading.Lock(); err = []
def part(a, b):
    for attempt in range(5):
        try:
            rq = urllib.request.Request(final, headers={"Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(rq, timeout=60) as r, open(out, "r+b") as f:
                f.seek(a)
                while True:
                    c = r.read(1 << 20)
                    if not c: break
                    f.write(c)
                    with lock: done[0] += len(c)
            return
        except Exception as e:
            err.append(str(e)); time.sleep(2)
    err.append("gave up")
step = total // N + 1
ts = [threading.Thread(target=part, args=(i * step, min(total, (i + 1) * step) - 1)) for i in range(N)]
[t.start() for t in ts]
t0 = time.time()
while any(t.is_alive() for t in ts):
    time.sleep(10); print(f"  {done[0]/1e9:.1f}/{total/1e9:.1f} GB  {done[0]/1e6/(time.time()-t0):.0f} MB/s", flush=True)
if "gave up" in err or done[0] < total: sys.exit("download incomplete")
PY
}
get() {  # url subdir file
  mkdir -p "$M/$2"; [ -s "$M/$2/$3" ] && { echo "have $3"; return; }
  echo "downloading $3"; if pget "$1" "$M/$2/$3.part"; then mv "$M/$2/$3.part" "$M/$2/$3"; else echo "FAILED $3"; rm -f "$M/$2/$3.part"; fi
}
echo "free space:"; df -h "$M" | tail -1
get $W21/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors text_encoders umt5_xxl_fp8_e4m3fn_scaled.safetensors
HY=https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files
for set in "${@:-5b}"; do
 echo "=== $set"
 case "$set" in
  5b) get $R/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors diffusion_models wan2.2_ti2v_5B_fp16.safetensors
      get $R/vae/wan2.2_vae.safetensors vae wan2.2_vae.safetensors ;;
  14b-i2v) get $R/vae/wan_2.1_vae.safetensors vae wan_2.1_vae.safetensors
      get $R/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors diffusion_models wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors
      get $R/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors diffusion_models wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors ;;
  hunyuan) get $HY/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors text_encoders qwen_2.5_vl_7b_fp8_scaled.safetensors
      get $HY/text_encoders/byt5_small_glyphxl_fp16.safetensors text_encoders byt5_small_glyphxl_fp16.safetensors
      get $HY/vae/hunyuanvideo15_vae_fp16.safetensors vae hunyuanvideo15_vae_fp16.safetensors
      get $HY/diffusion_models/hunyuanvideo1.5_720p_t2v_fp16.safetensors diffusion_models hunyuanvideo1.5_720p_t2v_fp16.safetensors
      get $HY/diffusion_models/hunyuanvideo1.5_720p_i2v_fp16.safetensors diffusion_models hunyuanvideo1.5_720p_i2v_fp16.safetensors
      get https://huggingface.co/Comfy-Org/sigclip_vision_384/resolve/main/sigclip_vision_patch14_384.safetensors clip_vision sigclip_vision_patch14_384.safetensors ;;
  ltx2) L=https://huggingface.co/Lightricks/LTX-2/resolve/main
      get $L/ltx-2-19b-distilled-fp8.safetensors checkpoints ltx-2-19b-distilled-fp8.safetensors
      get https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors text_encoders gemma_3_12B_it_fp4_mixed.safetensors
      get $L/ltx-2-spatial-upscaler-x2-1.0.safetensors latent_upscale_models ltx-2-spatial-upscaler-x2-1.0.safetensors ;;
  loras) W22=https://huggingface.co/Comfy-Org/Wan-2.2/resolve/main/split_files/loras
      get $W22/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors loras wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors
      get $W22/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors loras wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors
      get $HY/loras/hunyuanvideo1.5_t2v_480p_lightx2v_4step_lora_rank_32_bf16.safetensors loras hunyuanvideo1.5_t2v_480p_lightx2v_4step_lora_rank_32_bf16.safetensors ;;
  loras1022) LD=https://huggingface.co/lightx2v/Wan2.2-Distill-Loras/resolve/main
      get $LD/wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors loras wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors
      get $LD/wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors loras wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors ;;
  s2v) get $R/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors diffusion_models wan2.2_s2v_14B_fp8_scaled.safetensors
      get $R/audio_encoders/wav2vec2_large_english_fp16.safetensors audio_encoders wav2vec2_large_english_fp16.safetensors
      get $R/vae/wan_2.1_vae.safetensors vae wan_2.1_vae.safetensors
      get $R/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors loras wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors ;;
  flux2) get https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors diffusion_models flux-2-klein-4b-fp8.safetensors
      get https://huggingface.co/Comfy-Org/Flux-2-Klein-4B/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors text_encoders qwen_3_4b.safetensors
      get https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors vae flux2-vae.safetensors ;;
  int8) I8=https://huggingface.co/Winnougan/Wan2.2-INT8-Convrot/resolve/main
      get $I8/wan2.2_i2v_high_noise_14B_int8_convrot.safetensors diffusion_models wan2.2_i2v_high_noise_14B_int8_convrot.safetensors
      get $I8/wan2.2_i2v_low_noise_14B_int8_convrot.safetensors diffusion_models wan2.2_i2v_low_noise_14B_int8_convrot.safetensors ;;
  int8te) get https://huggingface.co/Winnougan/Wan2.2-INT8-Convrot/resolve/main/umt5_xxl_int8_convrot.safetensors text_encoders umt5_xxl_int8_convrot.safetensors ;;
  qwen21) Q=https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main
      get $Q/diffusion_models/qwen_image_2.1_int8_convrot.safetensors diffusion_models qwen_image_2.1_int8_convrot.safetensors
      get $Q/text_encoders/qwen3vl_8b_int8_convrot.safetensors text_encoders qwen3vl_8b_int8_convrot.safetensors
      get $Q/vae/qwen_image_2.1_vae_bf16.safetensors vae qwen_image_2.1_vae_bf16.safetensors
      get https://huggingface.co/lightx2v/Qwen-Image-2.1-Lightning/resolve/main/pytorch_lora_weights.safetensors loras qwen_image_2.1_lightning4.safetensors ;;
  int8s2v) get https://huggingface.co/Winnougan/Wan2.2-INT8-Convrot/resolve/main/wan2.2_s2v_14B_int8_convrot.safetensors diffusion_models wan2.2_s2v_14B_int8_convrot.safetensors ;;
 esac
done
echo done; ls -lh "$M"/audio_encoders "$M"/loras "$M"/diffusion_models "$M"/vae "$M"/text_encoders | grep -i -E "wan|umt5|hunyuan|qwen|byt5|sigclip|ltx|gemma|lightx2v|s2v|wav2vec|flux|qwen_3|int8"
