# Sourced by every script that talks to the 3090 box. The real values live in box.env (gitignored).
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$_d/box.env" ]; then echo "missing $_d/box.env - copy box.env.example to box.env and fill it in" >&2; exit 1; fi
. "$_d/box.env"
BOX_SSH="${BOX_USER}@${BOX_HOST}"
