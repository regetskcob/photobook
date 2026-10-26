# Delivering large files to the user's device

> **Only relevant when Claude works in a cloud workspace and reaches the
> user's files through a device bridge** (as for the Oberstdorf book).
> Running the engine locally, none of this applies.

Quick reference for the `mcp__remote-devices__*` tools (Cowork device
bridge).

## Limits

- `SendUserFile` (cloud workspace → conversation): **max 30 MiB per file**.
- `device_commit_files` (conversation → device): **max 20 MB per file AND
  max 100 MB total per call**.
- `device_bash` has **no network access** – no `git push`, no `curl`, no
  `pip install` from there. Local file operations and already-installed
  tools only.
- `device_bash` **cannot delete anything** (`rm`/`rmdir`/`unlink` fail).
  Cleanup only works via `mv` into a `_to_delete/` subfolder inside a
  connected folder — the user deletes it themselves afterward.

## Path trap in `device_bash`

`$HOME` inside `device_bash` is a session-scoped sandbox path, NOT the
user's real home directory. Connected folders show up under
`$HOME/mnt/<FolderName>/`. That's a different namespace than the `~/...`
paths used by `device_list_dir`/`device_stage_files`/`device_commit_files`
(which resolve `~` on the real device). Run `ls "$HOME/mnt/"` first to find
the actual mount name, then navigate from there.

## `git` on the bridged mount

The bridged mount doesn't support real `unlink()` — git's internal
lock-file and loose-object cleanup steps fail with "Operation not
permitted" warnings. In practice `git add`/`git commit` still succeed
functionally (verified with `git fsck --full` staying clean and
`git status` reflecting the change correctly) despite the noisy warnings,
but they leave stray `*.lock` files behind that block the *next* git
invocation ("Another git process seems to be running"). Workaround: before
each git call, move away any leftover lock file first (can't delete it,
only rename/move it):

```bash
cd repo
[ -f .git/index.lock ] && mv .git/index.lock ".git/index.lock.stale_$$"
git add -A
[ -f .git/index.lock ] && mv .git/index.lock ".git/index.lock.stale_$$_2"
git commit -m "..."
```

`git push` needs network, which `device_bash` doesn't have — do that step
by asking the user to run `git push` themselves (their local terminal has
their credentials and normal network access), rather than trying to
authenticate as them from the cloud container.

## Recipe: getting a file > 20 MB onto the device

```bash
# 1. Split into chunks comfortably under the 20 MB per-file limit AND the
#    100 MB per-call total (so 5 chunks fit in one device_commit_files
#    call). 18 MB chunks worked reliably in practice for a ~165 MB file
#    (10 chunks, delivered as two SendUserFile+device_commit_files batches
#    of 5) - don't cut it right up against either limit.
split -b 18000000 -d -a 3 BIG_FILE.pdf BIG_FILE_chunk_

# 2. Note the checksum of the original file for later verification
#    (sha256 or md5, either works - just be consistent on both ends)
sha256sum BIG_FILE.pdf
```

Then send every part via `SendUserFile` individually, collect the
returned `file_uuid`s, and use `device_commit_files` in batches
≤ 100 MB total to copy them onto the device (`force: true` if a stale
version already exists at the target path). A good target path pattern is
a scratch subfolder inside the destination, e.g. `review/vN/_transfer_x/`,
so the parts don't clutter the delivered files.

Reassemble and verify on the device:

```bash
# device_bash, in the target folder
cat BIG_FILE_chunk_000 BIG_FILE_chunk_001 ... > BIG_FILE.pdf
shasum -a 256 BIG_FILE.pdf   # must match the cloud-workspace checksum exactly
# clean up the parts (can't delete, so move them out of the way):
mkdir -p _to_delete/parts_x
mv BIG_FILE_chunk_* _to_delete/parts_x/ 2>/dev/null || true
```

This has been used repeatedly (multiple ~165 MB print-ready PDFs) with an
exact checksum match every time — reliable as long as every chunk from
`split` actually lands (double check `device_commit_files`'s response for
a `rejected` entry before reassembling).

## For pure review purposes: render small instead of chunking

If a file is only meant for reading/checking (not the final print file),
it's often better to keep it small rather than chunk it:
build it at low resolution in the first place (`--mode numbers` defaults to
110 dpi, any mode takes `--dpi`), or downscale an existing PDF:

```bash
pdftoppm -jpeg -jpegopt quality=72 -r 110 INPUT.pdf pages/p
python3 -c "
from PIL import Image
import glob
imgs = [Image.open(f).convert('RGB') for f in sorted(glob.glob('pages/p-*.jpg'))]
imgs[0].save('OUTPUT_small.pdf', save_all=True, append_images=imgs[1:])
"
```

A 165 MB print PDF typically shrinks to ~10–15 MB this way — fits in a
single `SendUserFile` call, no chunking logic needed. Don't use this for
the actual final print delivery (quality loss), only for interim
states/references.

## Reminder: final delivery only after explicit go-ahead

The actual final delivery of the print-ready PDFs (not review interim
states) should only happen after explicit user confirmation — that's a
repeatedly stated project-specific rule, not a technical constraint of
this document.
