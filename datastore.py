"""Safe JSON storage used by every data file in BizManager.

Why this exists
---------------
The old code did   open(file, "w"); json.dump(...)   and, on a read error,
quietly returned an empty dict.  Two bad things follow from that:

* If the app is stopped (or Render restarts it) in the middle of a write, the
  file is left half written.
* The next load then "succeeds" with {} and the next save overwrites the whole
  file with that empty data - one bad moment wipes a business.

Rules here:

* save_json()  writes to a temp file, flushes it to disk, keeps the previous
  good copy as <file>.bak, then swaps the new file in with os.replace(), which
  is atomic: readers see the old file or the new file, never half of one.
* load_json()  - missing file  -> the default value (first run)
               - unreadable file -> recover from <file>.bak
               - unreadable and no usable backup -> raise DataCorruptError
  It NEVER pretends a damaged file is empty.
"""

import json
import os
import shutil
import threading

_lock = threading.RLock()


class DataCorruptError(RuntimeError):
    """A data file is damaged and could not be recovered from its backup."""


def _fresh(default):
    return default() if callable(default) else (default if default is not None else {})


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path, default=None):
    with _lock:
        try:
            return _read(path)
        except FileNotFoundError:
            return _fresh(default)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            bak = path + ".bak"
            try:
                data = _read(bak)
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
                raise DataCorruptError(
                    f"{path} is damaged ({exc}) and there is no usable backup."
                ) from exc
            print(f"[datastore] {path} was damaged - recovered from {bak}")
            try:
                save_json(path, data)
            except OSError:
                pass
            return data


def save_json(path, data, indent=4):
    # Serialise first: if the data can't be turned into JSON we must not
    # touch the existing file at all.
    text = json.dumps(data, indent=indent)
    with _lock:
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        if os.path.exists(path):
            try:
                _read(path)                      # only back up a file that is good
                shutil.copyfile(path, path + ".bak")
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                pass
        os.replace(tmp, path)
