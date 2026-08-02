#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("inputs",nargs="*",type=Path);a=p.parse_args();merged=[]
 for path in a.inputs:
  if not path.is_file():continue
  data=json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(data,list):continue
  for item in data:
   if isinstance(item,dict):
    row=dict(item);row["id"]=len(merged);merged.append(row)
 merged.sort(key=lambda x:(float(x.get("start",0)),float(x.get("end",0))))
 for i,row in enumerate(merged):row["id"]=i
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding="utf-8");print(f"Merged subtitles: {len(merged)} -> {a.output}")
if __name__=="__main__":main()
