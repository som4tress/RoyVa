"""Benchmark llama-server flag variants / builds on a spare port (8010), leaving the live server alone.
Usage: LB=llama-b12250/llama-b12250 python3 -I tests/llama_bench.py base ngram-mod   (LB = build dir under ~/llm-server/llamacpp)"""
import json,subprocess,time,urllib.request,os,random,sys,signal
import os
LLM=os.environ.get("LARES_LLM_DIR") or os.path.expanduser("~/llm-server")
L=LLM+"/llamacpp"
env=dict(os.environ,LD_LIBRARY_PATH=f"{L}/compat/usr/lib/x86_64-linux-gnu:{L}/"+os.environ.get("LB","llama-b12110")+"")
BASE=["--model",LLM+"/models/Qwen3.6-35B-A3B-Q8_0.gguf","--host","127.0.0.1","--port","8010","--n-gpu-layers","999","--flash-attn","on","--ctx-size","32768","--parallel","1","--threads","8","--threads-batch","16","--jinja","--reasoning","off","--temp","0","--no-cache-prompt","--fit","off","--load-mode","mmap"]
VARIANTS={
 "base(b2048,ub1024)":["--batch-size","2048","--ubatch-size","1024"],
 "kv-q8":["--batch-size","2048","--ubatch-size","1024","-ctk","q8_0","-ctv","q8_0"],
 "ub2048":["--batch-size","4096","--ubatch-size","2048"],
 "ub512":["--batch-size","2048","--ubatch-size","512"],
 "ngram-mod":["--batch-size","2048","--ubatch-size","1024","--spec-type","ngram-mod"],
 "ngram-simple":["--batch-size","2048","--ubatch-size","1024","--spec-type","ngram-simple"],
}
only=sys.argv[1:] 
random.seed(7)
words=open("/usr/share/dict/words").read().split() if os.path.exists("/usr/share/dict/words") else [f"w{n}x{n*7%13}" for n in range(5000)]
def filler(n): return " ".join(random.choice(words) for _ in range(n))
P_DEC=("Explain how rain forms in detail.",200)
P_JSON=("Output a compact JSON array of 40 objects with keys id,name,status,area where name is 'light_N', status alternates on/off, area is 'living_room'. Output only JSON.",600)
P_PRE4=(filler(2800)+"\nIn one word, what is this?",8)
P_PRE16=(filler(4800)+"\nIn one word, what is this?",8)
def comp(p,n):
    r=urllib.request.Request("http://127.0.0.1:8010/completion",json.dumps({"prompt":p,"n_predict":n,"temperature":0,"cache_prompt":False}).encode(),{"content-type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=600))
res={}
for name,args in VARIANTS.items():
    if only and not any(o in name for o in only): continue
    log=open(f"/tmp/lb-{name.split('(')[0]}.log","w")
    pr=subprocess.Popen([f"{L}/"+os.environ.get("LB","llama-b12110")+"/llama-server"]+BASE+args,env=env,stdout=log,stderr=log)
    t0=time.time(); ok=False
    while time.time()-t0<300:
        try: urllib.request.urlopen("http://127.0.0.1:8010/health",timeout=2); ok=True; break
        except Exception: time.sleep(3)
    row={"load_s":round(time.time()-t0)}
    if ok:
        comp("warm up",4)
        try:
            for k,(p,n) in {"dec":P_DEC,"json":P_JSON,"pre4k":P_PRE4,"pre16k":P_PRE16}.items():
                tm=comp(p,n)["timings"]
                row[k]=(round(tm["predicted_per_second"],1) if k in("dec","json") else round(tm["prompt_per_second"]))
                if k=="json": row["json_n"]=tm["predicted_n"]
        except Exception as e: row["err"]=str(e)[:80]
    pr.send_signal(signal.SIGINT); 
    try: pr.wait(30)
    except Exception: pr.kill()
    res[name]=row; print(name,row,flush=True); time.sleep(5)
