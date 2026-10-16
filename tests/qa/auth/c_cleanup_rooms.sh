#!/bin/sh
# Xoa phong lop hoc thu (tieu de qa_stab_*) trong sqlite cua ai-trading (khong co API xoa). Dung: sh tests/qa/auth/c_cleanup_rooms.sh
docker exec -i tradingsys-ai-trading python - <<'PY'
import sqlite3,glob
for f in glob.glob('/classroom/*.db'):
    try:
        c=sqlite3.connect(f); r=c.execute("select id from class_rooms where title like 'qa_stab_%'").fetchall()
    except Exception: continue
    for (i,) in r:
        for t,col in (("class_messages","room_id"),("class_members","room_id"),("class_rooms","id")):
            try: c.execute(f"delete from {t} where {col}=?",(i,))
            except Exception as e: print(t,e)
    c.commit(); print(f,len(r),"phong xoa")
PY
