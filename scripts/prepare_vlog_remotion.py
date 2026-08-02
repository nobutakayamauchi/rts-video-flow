#!/usr/bin/env python3
"""Prepare a manifest-driven Remotion project for the lightweight Vlog flow."""
from __future__ import annotations
import argparse,json,shutil,subprocess,sys
from pathlib import Path
from typing import Any
FPS=30; DEFAULT_WIDTH=1920; DEFAULT_HEIGHT=1080

def fail(m:str)->None: print(f"ERROR: {m}",file=sys.stderr); raise SystemExit(1)
def parse_args():
 p=argparse.ArgumentParser(); p.add_argument("project",type=Path); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--subtitles",type=Path,required=True); p.add_argument("--remotion-dir",type=Path,default=Path("remotion-project")); p.add_argument("--width",type=int,default=DEFAULT_WIDTH); p.add_argument("--height",type=int,default=DEFAULT_HEIGHT); return p.parse_args()
def probe(path:Path)->float:
 try:
  r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],check=True,capture_output=True,text=True); return max(.1,float(r.stdout.strip()))
 except Exception as e: fail(f"Could not read duration for {path}: {e}")
def load(path:Path)->Any:
 try:return json.loads(path.read_text(encoding="utf-8"))
 except Exception as e: fail(f"Could not read {path}: {e}")
def safe(i:int,p:Path)->str:return f"{i:03d}-{p.stem[:48]}{p.suffix.lower() or '.bin'}"
def build(project:Path,manifest:dict[str,Any],public:Path):
 raw=manifest.get("timeline");
 if not isinstance(raw,list) or not raw: fail("Manifest timeline is empty")
 public.mkdir(parents=True,exist_ok=True); out=[]; cursor=0.0
 for i,item in enumerate(raw):
  if not isinstance(item,dict):continue
  sv=item.get("source"); typ=item.get("type")
  if not isinstance(sv,str) or typ not in {"video","image"}:continue
  src=project/sv
  if not src.is_file():fail(f"Missing asset: {src}")
  name=safe(i,src); shutil.copy2(src,public/name)
  duration=float(item.get("resolvedDuration",item.get("durationSeconds",probe(src) if typ=="video" else 5.0)))
  narration_name=None
  nv=item.get("narration")
  if isinstance(nv,str) and nv:
   np=project/nv
   if not np.is_file(): fail(f"Missing narration: {np}")
   narration_name=f"narration-{i:03d}{np.suffix.lower() or '.webm'}"; shutil.copy2(np,public/narration_name)
  out.append({"id":i,"type":typ,"role":str(item.get("role","asset")),"src":name,"start":round(cursor,3),"duration":round(duration,3),"motion":str(item.get("motion","none")),"narration":narration_name,"explanation":str(item.get("explanation","")).strip()})
  cursor+=duration
 if not out:fail("No valid assets")
 return out,cursor
def root_tsx(w,h,d): return f'''import React from "react";\nimport {{Composition}} from "remotion";\nimport {{VlogVideo}} from "./VlogVideo";\nexport const RemotionRoot:React.FC=()=> <Composition id="VlogVideo" component={{VlogVideo}} fps={FPS} width={w} height={h} durationInFrames={d}/>;\n'''
def vlog_tsx(): return '''import React from "react";
import {AbsoluteFill,Audio,Img,OffthreadVideo,Sequence,interpolate,staticFile,useCurrentFrame} from "remotion";
import timeline from "../public/vlog/timeline.json";
import subtitles from "../public/vlog/subtitles.json";
type T={id:number;type:"video"|"image";role:string;src:string;start:number;duration:number;motion:string;narration:string|null;explanation:string};
type S={id:number;start:number;end:number;lines:string[];fontSize:number};
const FPS=30, media=timeline as T[], captions=subtitles as S[];
const Still:React.FC<{item:T}>=({item})=>{const f=useCurrentFrame(),d=Math.max(1,Math.round(item.duration*FPS)),s=item.motion==="slow-pan"?interpolate(f,[0,d],[1,1.06],{extrapolateRight:"clamp"}):1;return <AbsoluteFill style={{backgroundColor:"#05070a",overflow:"hidden",display:"flex",flexDirection:"row"}}><div style={{width:item.explanation?"72%":"100%",height:"100%",display:"flex",alignItems:"center",justifyContent:"center"}}><Img src={staticFile(`vlog/assets/${item.src}`)} style={{width:"100%",height:"100%",objectFit:"contain",transform:`scale(${s})`}}/></div>{item.explanation&&<div style={{width:"28%",padding:42,boxSizing:"border-box",background:"#111923",color:"white",display:"flex",alignItems:"center",fontSize:34,fontWeight:700,lineHeight:1.5}}>{item.explanation}</div>}</AbsoluteFill>};
export const VlogVideo:React.FC=()=>{const frame=useCurrentFrame();return <AbsoluteFill style={{backgroundColor:"black"}}>{media.map(item=>{const from=Math.round(item.start*FPS),dur=Math.max(1,Math.round(item.duration*FPS));return <Sequence key={item.id} from={from} durationInFrames={dur}>{item.type==="video"?<OffthreadVideo src={staticFile(`vlog/assets/${item.src}`)} style={{width:"100%",height:"100%",objectFit:"contain"}}/>:<Still item={item}/>} {item.narration&&<Audio src={staticFile(`vlog/assets/${item.narration}`)}/>}</Sequence>})}{captions.map(c=>{const from=Math.round(c.start*FPS),dur=Math.max(1,Math.round((c.end-c.start)*FPS));if(frame<from||frame>=from+dur)return null;return <Sequence key={c.id} from={from} durationInFrames={dur}><AbsoluteFill style={{justifyContent:"flex-end",alignItems:"center",paddingBottom:54}}><div style={{maxWidth:"88%",padding:"12px 22px",borderRadius:14,backgroundColor:"rgba(0,0,0,.72)",color:"white",fontSize:Math.min(c.fontSize,56),fontWeight:800,lineHeight:1.25,textAlign:"center",whiteSpace:"pre-line",textShadow:"0 2px 8px rgba(0,0,0,.9)"}}>{c.lines.join("\\n")}</div></AbsoluteFill></Sequence>})}</AbsoluteFill>};
'''
def main():
 a=parse_args(); project=a.project.resolve(); manifest=load(a.manifest.resolve()); subs=load(a.subtitles.resolve()); rem=a.remotion_dir.resolve()
 if not isinstance(manifest,dict) or not isinstance(subs,list):fail("Invalid manifest or subtitles")
 pub=rem/"public"/"vlog"; assets=pub/"assets"
 if assets.exists():shutil.rmtree(assets)
 tl,total=build(project,manifest,assets); pub.mkdir(parents=True,exist_ok=True)
 (pub/"timeline.json").write_text(json.dumps(tl,ensure_ascii=False,indent=2),encoding="utf-8"); (pub/"subtitles.json").write_text(json.dumps(subs,ensure_ascii=False,indent=2),encoding="utf-8")
 src=rem/"src";src.mkdir(parents=True,exist_ok=True);frames=max(1,round(total*FPS));(src/"Root.tsx").write_text(root_tsx(a.width,a.height,frames),encoding="utf-8");(src/"VlogVideo.tsx").write_text(vlog_tsx(),encoding="utf-8");(src/"index.ts").write_text('import {registerRoot} from "remotion";\nimport {RemotionRoot} from "./Root";\nregisterRoot(RemotionRoot);\n',encoding="utf-8")
 print(f"Prepared {len(tl)} timeline items\nTotal duration: {total:.3f} sec\nFrames: {frames}")
if __name__=="__main__":main()
