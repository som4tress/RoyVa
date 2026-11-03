from pathlib import Path
import re
import shutil

home = Path.home().resolve()
scratch = (home / 'llm-server/image-layers').resolve(strict=True)
if scratch.parent != home / 'llm-server':
    raise RuntimeError('Unexpected image scratch location')
removed = 0
for path in scratch.iterdir():
    if re.fullmatch('[0-9a-f]{64}(?:\\.partial)?', path.name) and path.is_file() and not path.is_symlink():
        removed += path.stat().st_size
        path.unlink()
hub = (home / '.cache/huggingface/hub').resolve(strict=True)
partial = hub / 'models--Qwen--Qwen3.6-35B-A3B-FP8'
if partial.exists():
    if partial.is_symlink() or partial.resolve().parent != hub:
        raise RuntimeError('Unexpected interrupted-download location')
    shutil.rmtree(partial)
print('Removed temporary layer files and interrupted FP8 download; retained INT8 originals and provenance.')
