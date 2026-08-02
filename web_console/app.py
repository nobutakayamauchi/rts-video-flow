#!/usr/bin/env python3
"""Mobile-first web console for assembling and rendering lightweight Vlogs."""
from __future__ import annotations
import json,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from fastapi import FastAPI,File,Form,HTTPException,UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
ROOT=Path(__file__).resolve().parent.parent;STATIC_DIR=Path(__file__).resolve().parent/"static";PROJECTS_DIR=ROOT/"projects";OUTPUT_DIR=ROOT/"output"
ALLOWED_ROLES={"opening","ending","camera","screen","screenshot"};MAX_UPLOAD_BYTES=500*1024*1024
app=FastAPI(title="RTS Vlog Web Console");app.mount("/static",StaticFiles(directory=STATIC_DIR),name="static")
def safe_project_name(v:str)->str:
 c=re.sub(r"[^A-Za-z0-9._-]+","-",v.strip()).strip("-.")
 if not c:raise HTTPException(status_code=400,detail="Invalid project name")
 return c[:80]
def extension_for(ct:str|None,fn:str|None=None)->str:
 s=Path(fn or "").suffix.lower()
 if s in {".mp4",".mov",".m4v",".webm",".jpg",".jpeg",".png",".webp",".m4a",".wav",".ogg"}:return s
 return {"video/mp4":".mp4","video/quicktime":".mov","video/webm":".webm","image/jpeg":".jpg","image/png":".png","image/webp":".webp","audio/mp4":".m4a","audio/webm":".webm","audio/ogg":".ogg","audio/wav":".wav"}.get((ct or "").lower(),".bin")
def project_dir(n:str)->Path:return PROJECTS_DIR/safe_project_name(n)
def plan_path(p:Path)->Path:return p/"vlog-plan.json"
def default_plan(n:str)->dict[str,Any]:return {"version":3,"project":n,"policy":{"screenRecording":"short-demo-only","defaultEvidence":"screenshots","privacyReviewRequired":True},"timeline":[]}
def load_plan(p:Path)->dict[str,Any]:
 path=plan_path(p)
 if not path.is_file():return default_plan(p.name)
 try:x=json.loads(path.read_text(encoding="utf-8"))
 except json.JSONDecodeError as e:raise HTTPException(status_code=500,detail=f"Invalid project plan: {e}") from e
 if not isinstance(x,dict) or not isinstance(x.get("timeline"),list):raise HTTPException(status_code=500,detail="Invalid project plan structure")
 return x
def save_plan(p:Path,x:dict[str,Any])->None:p.mkdir(parents=True,exist_ok=True);plan_path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def target_folder(p:Path,r:str)->Path:
 if r in {"opening","ending","camera"}:return p/"camera"
 if r=="screen":return p/"screen"
 return p/"screenshots"
def timestamp()->str:return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
@app.get("/")
def index()->FileResponse:return FileResponse(STATIC_DIR/"index.html")
@app.get("/api/project/{project_name}")
def project_status(project_name:str)->dict[str,Any]:
 p=project_dir(project_name);x=load_plan(p);return {"project":p.name,"timeline":x["timeline"],"outputExists":(OUTPUT_DIR/p.name/"vlog.mp4").is_file()}
@app.post("/api/material")
async def save_material(project:str=Form(...),role:str=Form(...),description:str=Form(""),media:UploadFile=File(...))->dict[str,Any]:
 p=project_dir(project)
 if role not in ALLOWED_ROLES:raise HTTPException(status_code=400,detail="Unsupported role")
 data=await media.read()
 if not data:raise HTTPException(status_code=400,detail="Empty media")
 if len(data)>MAX_UPLOAD_BYTES:raise HTTPException(status_code=413,detail="Media is too large")
 plan=load_plan(p);folder=target_folder(p,role);folder.mkdir(parents=True,exist_ok=True);ext=extension_for(media.content_type,media.filename);order=len(plan["timeline"])+1;target=folder/f"{order:02d}-{role}-{timestamp()}{ext}";target.write_bytes(data)
 item={"id":f"item-{timestamp()}-{order}","type":"image" if role=="screenshot" else "video","source":str(target.relative_to(p)),"role":role}
 if description.strip():item["explanation"]=description.strip()
 if role=="screenshot":item.update({"durationSeconds":5.0,"motion":"slow-pan"})
 plan["timeline"].append(item);save_plan(p,plan);return {"status":"saved","item":item,"timeline":plan["timeline"]}
@app.post("/api/narration")
async def save_narration(project:str=Form(...),item_id:str=Form(...),transcript_hint:str=Form(""),media:UploadFile=File(...))->dict[str,Any]:
 p=project_dir(project);plan=load_plan(p);item=next((x for x in plan["timeline"] if x.get("id")==item_id),None)
 if not item:raise HTTPException(status_code=404,detail="Timeline item not found")
 if item.get("type")!="image":raise HTTPException(status_code=400,detail="Narration recording is only supported for screenshots")
 data=await media.read()
 if not data:raise HTTPException(status_code=400,detail="Empty narration")
 if len(data)>MAX_UPLOAD_BYTES:raise HTTPException(status_code=413,detail="Narration is too large")
 folder=p/"narration";folder.mkdir(parents=True,exist_ok=True);ext=extension_for(media.content_type,media.filename);target=folder/f"{item_id}-{timestamp()}{ext}";target.write_bytes(data);item["narration"]=str(target.relative_to(p))
 if transcript_hint.strip():item["transcriptHint"]=transcript_hint.strip()
 save_plan(p,plan);return {"status":"saved","item":item}
@app.post("/api/reorder")
def reorder(project:str=Form(...),ordered_ids:str=Form(...))->dict[str,Any]:
 p=project_dir(project);plan=load_plan(p);ids=[v for v in ordered_ids.split(",") if v];by={str(i.get("id")):i for i in plan["timeline"]}
 if set(ids)!=set(by):raise HTTPException(status_code=400,detail="Order does not match timeline items")
 plan["timeline"]=[by[i] for i in ids];save_plan(p,plan);return {"status":"saved","timeline":plan["timeline"]}
@app.post("/api/compile")
def compile_vlog(project:str=Form(...),render:bool=Form(True))->dict[str,str]:
 p=project_dir(project);plan=load_plan(p);roles=[i.get("role") for i in plan["timeline"]]
 if "opening" not in roles:raise HTTPException(status_code=400,detail="Opening video is required")
 if "ending" not in roles:raise HTTPException(status_code=400,detail="Ending video is required")
 try:
  proc=subprocess.run(["bash",str(ROOT/"scripts"/"process_vlog.sh"),str(p)],cwd=ROOT,check=True,capture_output=True,text=True,timeout=3600);rlog=""
  if render:
   rr=subprocess.run(["bash",str(ROOT/"scripts"/"render_vlog.sh"),p.name],cwd=ROOT,check=True,capture_output=True,text=True,timeout=3600);rlog=rr.stdout[-4000:]
 except subprocess.TimeoutExpired as e:raise HTTPException(status_code=504,detail="Compilation timed out") from e
 except subprocess.CalledProcessError as e:raise HTTPException(status_code=500,detail=(e.stderr or e.stdout or str(e))[-4000:]) from e
 out=OUTPUT_DIR/p.name/"vlog.mp4";return {"status":"rendered" if render else "prepared","output":str(out.relative_to(ROOT)) if out.is_file() else "","processLog":proc.stdout[-4000:],"renderLog":rlog}
@app.get("/api/download/{project_name}")
def download(project_name:str)->FileResponse:
 n=safe_project_name(project_name);t=OUTPUT_DIR/n/"vlog.mp4"
 if not t.is_file():raise HTTPException(status_code=404,detail="Rendered video not found")
 return FileResponse(t,media_type="video/mp4",filename=f"{n}.mp4")
