"""Crude pyflakes: names read in a file that are bound nowhere in it (and are not builtins). Catches missing imports and typos."""
import ast, builtins, sys
bad = 0
for path in sys.argv[1:]:
    tree = ast.parse(open(path).read())
    bound = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): bound.add(n.name)
        if isinstance(n, ast.arg): bound.add(n.arg)
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)): bound.add(n.id)
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names: bound.add((a.asname or a.name).split(".")[0])
        if isinstance(n, ast.ExceptHandler) and n.name: bound.add(n.name)
        if isinstance(n, (ast.Global, ast.Nonlocal)): bound.update(n.names)
        if isinstance(n, ast.MatchAs) and n.name: bound.add(n.name)
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound:
            print(f"{path}:{n.lineno}: undefined name {n.id}")
            bad += 1
sys.exit(1 if bad else 0)
