from pathlib import Path
p=Path.home()/'.config/opencode/lib/procedure-memory.mjs';s=p.read_text()
s=s.replace("if(/token|password|secret|authorization|cookie|api.?key|credential|content|new.?string|old.?string|patch|code/i.test(key))", "if(/token|password|secret|authorization|cookie|api.?key|credential|(?:^|_)key$|content|new.?string|old.?string|patch|code/i.test(key))")
s=s.replace("if(/authorization\\s*[:=]|https?:\\/\\/[^\\s/]+:[^\\s@]+@|bearer\\s|eyJ[a-zA-Z0-9_-]{10,}\\.|(?:password|token|api[_-]?key|secret)\\s*[=:]/i.test(x))", "if(/password|\\bpwd\\b|token|secret|credential|api.?key|authorization|sshpass|[a-z][a-z0-9+.-]*:\\/\\/[^\\s/]+:[^\\s@]+@|bearer\\s|eyJ[a-zA-Z0-9_-]{10,}\\.|\\bsk-[a-zA-Z0-9_-]{8,}|api\\.telegram\\.org\\/bot\\d+:/i.test(x))")
p.write_text(s)
