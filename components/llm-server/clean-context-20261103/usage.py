import importlib.machinery,json,sys
m=importlib.machinery.SourceFileLoader('usage','/home/somdutta/.config/opencode/scripts/openrouter-usage').load_module()
print(json.dumps(m.collect(m.DEFAULT_DB,sys.argv[1],since_ms=int(sys.argv[2]))))
