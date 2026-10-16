"""Don phong thu qa_stab_ (SQLite /classroom, media, kich ban CL- do phong thu tao). Chay trong tradingsys-ai-trading:
   docker exec -i tradingsys-ai-trading python - < tests/qa/f_cleanup.py"""
import os, sqlite3, glob
root = os.environ.get("AI_CLASS_DIR", "/classroom")
dbs = glob.glob(root + "/*.db") + glob.glob(root + "/*.sqlite*")
print(dbs)
for p in dbs:
    c = sqlite3.connect(p)
    try:
        ids = [r[0] for r in c.execute("SELECT id FROM class_rooms WHERE title LIKE '%qa_stab%'")]
    except Exception as e:
        print(p, e); continue
    files = []
    for rid in ids:
        files += [r[0] for r in c.execute("SELECT file FROM class_attachments WHERE room_id=?", (rid,))]
        for t in ("class_members", "class_messages", "class_examples", "class_labels", "class_profiles", "class_profile_versions", "class_actions", "class_attachments", "class_audit"):
            c.execute(f"DELETE FROM {t} WHERE room_id=?", (rid,))
        c.execute("DELETE FROM class_rooms WHERE id=?", (rid,))
    for t in ("class_ux_confirm",):
        try:
            for rid in ids: c.execute(f"DELETE FROM {t} WHERE room_id=?", (rid,))
        except Exception: pass
    c.commit()
    for f in files:
        for q in (f, os.path.join(root, "media", f)):
            try: os.remove(q)
            except OSError: pass
    print("da xoa", len(ids), "phong", len(files), "tep")

# --- kich ban / job thu cua tab AI Trading (/state)
import json, shutil
st = os.environ.get("AI_STATE_DIR", "/state")
gone = set()
for d in glob.glob(st + "/scenarios/*"):
    try: by = json.load(open(d + "/meta.json")).get("created_by", "")
    except Exception: by = ""
    if os.path.basename(d).startswith("qa_stab_") or str(by).startswith("qa_stab_"):
        gone.add(os.path.basename(d)); shutil.rmtree(d, ignore_errors=True); print("xoa", d)
for p in glob.glob(st + "/jobs/*.json"):
    try:
        sid = str(json.load(open(p)).get("scenario_id", ""))
        if sid in gone or sid.startswith("qa_stab_"):
            os.remove(p); print("xoa job", p)
    except Exception as e: print(p, e)
