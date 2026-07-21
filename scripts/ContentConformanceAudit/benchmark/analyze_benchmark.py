# -*- coding: utf-8 -*-
import csv, re, os, json, statistics as st
CC = r"N:\Design Technology Resources\01_BIM CONTENT\Content Conformance"
AUD = CC + r"\1_AUDITED\_benchmark_Others_20260721_1816.csv"
CLE = CC + r"\3_CLEANED\_benchmark_3_Cleaned_20260721_1706.csv"
CLE0 = CC + r"\3_CLEANED\_benchmark_3_Cleaned_20260630_1612.csv"
GUA0 = CC + r"\2_GUARDIAN PASS\_benchmark_2_Guardian_Pass_20260630_1555.csv"

def kb(s):
    s=(s or "").replace(",","").strip()
    m=re.match(r"([\d.]+)\s*(KB|MB|GB)?",s,re.I)
    if not m: return 0.0
    v=float(m.group(1)); u=(m.group(2) or "KB").upper()
    return v*1024 if u=="MB" else v*1024*1024 if u=="GB" else v
def load(p):
    if not os.path.exists(p): return []
    return list(csv.DictReader(open(p,encoding="utf-8-sig",errors="replace")))
def num(r,k):
    try: return float((r.get(k) or "0").replace(",",""))
    except: return 0.0
def cat(r):
    rp=r.get("Relative Path","")
    return rp.split("\\")[0] if "\\" in rp else "(root)"

def agg(rows):
    if not rows: return {}
    n=len(rows)
    sizes=[kb(r["File Size"]) for r in rows]
    nested=[int(num(r,"Nested Families")) for r in rows]
    scores=[num(r,"Final Score") for r in rows if r.get("Final Score")]
    return dict(
        n=n,
        total_mb=round(sum(sizes)/1024,1), avg_kb=round(sum(sizes)/n),
        med_kb=round(st.median(sizes)), max_kb=round(max(sizes)),
        nested_total=sum(nested), nested_avg=round(sum(nested)/n,1), nested_max=max(nested),
        nested_fams=sum(1 for x in nested if x>0),
        cad=sum(1 for r in rows if num(r,"Imported CAD")>0),
        cad_total=int(sum(num(r,"Imported CAD") for r in rows)),
        raster=sum(1 for r in rows if num(r,"Raster Images")>0),
        modelgroups=sum(1 for r in rows if num(r,"Model Groups")>0),
        unnamed_rp=int(sum(num(r,"Unnamed Ref Planes") for r in rows)),
        unused=int(sum(num(r,"Unused Type Params")+num(r,"Unused Inst Params") for r in rows)),
        unused_fams=sum(1 for r in rows if (num(r,"Unused Type Params")+num(r,"Unused Inst Params"))>0),
        formula=int(sum(num(r,"Formula Params") for r in rows)),
        errors=sum(1 for r in rows if (r.get("Error") or "").strip()),
        score_avg=round(sum(scores)/len(scores),1) if scores else 0,
        score_min=round(min(scores),1) if scores else 0,
        score_max=round(max(scores),1) if scores else 0,
    )

aud=load(AUD); cle=load(CLE); cle0=load(CLE0); gua0=load(GUA0)
A=agg(aud); C=agg(cle); C0=agg(cle0); G0=agg(gua0)

# category breakdown for AUDITED
cats={}
for r in aud:
    c=cat(r)
    d=cats.setdefault(c,{"n":0,"mb":0.0,"nested":0,"scores":[],"cad":0})
    d["n"]+=1; d["mb"]+=kb(r["File Size"])/1024; d["nested"]+=int(num(r,"Nested Families"))
    if r.get("Final Score"): d["scores"].append(num(r,"Final Score"))
    if num(r,"Imported CAD")>0: d["cad"]+=1
catrows=[]
for c,d in sorted(cats.items(), key=lambda x:-x[1]["n"]):
    catrows.append((c,d["n"],round(d["mb"],1),d["nested"],
                    round(sum(d["scores"])/len(d["scores"]),1) if d["scores"] else 0))

# extremes
def topn(rows,key,rev=True,k=6):
    return sorted(rows,key=key,reverse=rev)[:k]
largest=[(r["Family Name"],round(kb(r["File Size"])/1024,2),int(num(r,"Nested Families"))) for r in topn(aud,lambda r:kb(r["File Size"]))]
mostnested=[(r["Family Name"],int(num(r,"Nested Families")),round(kb(r["File Size"])/1024,2)) for r in topn(aud,lambda r:num(r,"Nested Families"))]
worst=[(r["Family Name"],round(num(r,"Final Score"),1)) for r in topn([r for r in aud if r.get("Final Score")],lambda r:num(r,"Final Score"),rev=False)]

# Audited -> Cleaned per-family delta (families in both, by name)
cle_by={r["Family Name"]:r for r in cle}
imp=[]
for r in aud:
    o=cle_by.get(r["Family Name"])
    if o:
        ds=kb(r["File Size"])-kb(o["File Size"])
        dsc=num(o,"Final Score")-num(r,"Final Score")
        imp.append((r["Family Name"],round(ds/1024,2),round(dsc,1)))
improved_size=sum(1 for _,ds,_ in imp if ds>0.01)
saved_mb=round(sum(ds for _,ds,_ in imp if ds>0)/1,2)

# dedup savings: sizes in _DUPLICATES across stages
dup_mb=0.0; dup_n=0
for stage in ["1_AUDITED","2_GUARDIAN PASS","3_CLEANED"]:
    for root,_,fs in os.walk(os.path.join(CC,stage)):
        if os.path.basename(root).lower()=="_duplicates":
            for f in fs:
                if f.lower().endswith(".rfa"):
                    dup_mb+=os.path.getsize(os.path.join(root,f))/1024/1024; dup_n+=1

out=dict(AUDITED=A, CLEANED_now=C, CLEANED_jun30=C0, GUARDIAN_jun30=G0,
         categories=catrows, largest=largest, mostnested=mostnested, worst=worst,
         matched_aud_cle=len(imp), improved_size=improved_size, saved_mb=round(saved_mb,2),
         dup_files=dup_n, dup_mb=round(dup_mb,2))
open(r"C:\Users\fsun\AppData\Local\Temp\claude\c--Users-fsun-Documents-GitHub-BIMAutomations\1b4d7225-e9e7-4c8b-9949-dd2b4e6f2555\scratchpad\bench_stats.json","w").write(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
