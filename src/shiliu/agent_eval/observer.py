"""Optional bounded best-effort private capture; never required by a run.

Transport attempts are not proof of provider receipt. A full queue or process
exit may lose events, which must be treated as missing evidence.
"""
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import stat
import threading
import uuid
import time
import hashlib

context = ContextVar('eval_observer_context', default=None)
_events = queue.Queue(maxsize=256)
_start_lock = threading.Lock()
_worker = None

def enabled():
    return bool(os.environ.get('SHILIU_EVAL_OBSERVER_DIR'))

def _write(base, payload):
    root=Path(base)
    if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)): return
    info=root.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077: return
    encoded=json.dumps(payload,ensure_ascii=False,default=str,separators=(',',':')).encode('utf-8')
    name=uuid.uuid4().hex
    path=root/(name+'.pending')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as f: f.write(encoded)
    os.rename(path,root/(name+'.json'))

def _consume():
    while True:
        base,payload=_events.get()
        try: _write(base,payload)
        except Exception: pass
        finally: _events.task_done()

def record(event, **fields):
    global _worker
    try:
        base=os.environ.get('SHILIU_EVAL_OBSERVER_DIR')
        ctx=context.get()
        if not base or not ctx: return
        if isinstance(fields.get('body'),dict):
            fields['request_hash']=hashlib.sha256(json.dumps(fields['body'],sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode('utf-8')).hexdigest()
        payload=deepcopy({'event':event,'at':datetime.now(timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns(),**ctx,**fields})
        with _start_lock:
            if _worker is None:
                _worker=threading.Thread(target=_consume,name='eval-observer',daemon=True)
                _worker.start()
        _events.put_nowait((base,payload))
    except Exception:
        return

def record_for(ctx, event, **fields):
    token=context.set(ctx)
    try: record(event, **fields)
    finally: context.reset(token)


def candidate_snapshot(candidate):
    """Construct only when enabled; malformed observation must not escape."""
    if not enabled(): return
    try:
        record('prepared_context', body=candidate.request.body, metadata=candidate.metadata,
               message_ids=candidate.message_ids, context_revision=candidate.state.get('revision'))
    except Exception: pass
