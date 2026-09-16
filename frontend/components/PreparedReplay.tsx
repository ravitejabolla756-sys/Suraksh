"use client";

import { useEffect, useRef, useState } from "react";
import type { Camera } from "@/lib/api";

type TrackedObject = { id: number; box: number[]; class_id: number; confidence: number };
type Sample = { frame: number; source_timestamp?: number; objects: TrackedObject[] };
type Tracks = { fps: number; width: number; height: number; step: number; frames: Sample[]; model: string; tracker?: string; mode?: string };
const classes: Record<number,string> = {0:"Person",2:"Car",3:"Motorcycle",5:"Bus",7:"Truck"};

export function PreparedReplay({ camera }: { camera: Camera }) {
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [tracks, setTracks] = useState<Tracks | null>(null);
  const [message, setMessage] = useState("Preparing analysis; original video plays at normal speed.");
  const [annotations, setAnnotations] = useState(true);
  const [ids, setIds] = useState(true);
  const [counts, setCounts] = useState({people:0,vehicles:0});

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${camera.source_url}/tracks`, {signal:controller.signal,cache:"no-store"});
        if (!response.ok) throw new Error(response.status === 409 ? "Analysis is being prepared. Video plays at normal speed." : "Analysis unavailable; retrying.");
        const data: Tracks = await response.json();
        const ordered = data.frames.every((sample, index) => {
          const previous = data.frames[index - 1];
          return index === 0 || (previous !== undefined && sample.frame > previous.frame &&
            (sample.source_timestamp == null || previous.source_timestamp == null ||
             sample.source_timestamp > previous.source_timestamp));
        });
        if (!ordered) throw new Error("Analysis rejected: source frame order is invalid.");
        if (!cancelled) { setTracks(data); setMessage(`${data.model} + ${data.tracker ?? "timestamp-aware tracker"} · prepared replay · 1× source playback`); }
      } catch (error) {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Analysis unavailable");
          timer = setTimeout(load,5000);
        }
      }
    }
    void load();
    return () => {cancelled=true;clearTimeout(timer);controller.abort();};
  },[camera.source_url]);

  useEffect(() => {
    const player = video.current;
    const overlay = canvas.current;
    if (!player || !overlay || !tracks) return;
    overlay.width = tracks.width; overlay.height = tracks.height;
    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    let callback = 0;
    let stopped = false;
    let lastSample = -1;
    function draw(time: number) {
      if (!ctx || !overlay || !tracks) return;
      ctx.clearRect(0,0,overlay.width,overlay.height);
      const frame = time * tracks.fps;
      // Binary search also handles seek, pause and looping.
      let low=0, high=tracks.frames.length-1;
      while (low<high) {const mid=Math.ceil((low+high)/2);if(tracks.frames[mid].frame<=frame)low=mid;else high=mid-1;}
      const a=tracks.frames[low], b=tracks.frames[Math.min(low+1,tracks.frames.length-1)];
      if (!a) return;
      const aTime = a.source_timestamp ?? a.frame / tracks.fps;
      const bTime = b.source_timestamp ?? b.frame / tracks.fps;
      // Never keep an older analysis attached after playback has passed its
      // source-time interval. This prevents frame N from carrying state from
      // an unrelated earlier sample when cache/video timelines diverge.
      if (time < aTime || (low < tracks.frames.length - 1 && time > bTime)) {
        if (low!==lastSample) { lastSample=low; setCounts({people:0,vehicles:0}); }
        return;
      }
      if (low!==lastSample) {
        lastSample=low;
        setCounts({people:a.objects.filter(o=>o.class_id===0).length,vehicles:a.objects.filter(o=>o.class_id!==0).length});
      }
      if (!annotations) return;
      const ratio=b.frame>a.frame?Math.min(1,Math.max(0,(frame-a.frame)/(b.frame-a.frame))):0;
      const next=new Map(b.objects.map(o=>[o.id,o]));
      for(const item of a.objects) {
        const end=next.get(item.id);
        // Keep an object visible through a short detector gap, but do not
        // invent boxes for the entire interval when a track really ended.
        if (!end && ratio > 0.45) continue;
        const box=item.box.map((v,i)=>end?v+(end.box[i]-v)*ratio:v);
        ctx.strokeStyle=item.class_id===0?"#42d392":"#ffad52";
        ctx.lineWidth=2;
        ctx.strokeRect(box[0],box[1],box[2]-box[0],box[3]-box[1]);
        ctx.fillStyle=ctx.strokeStyle;ctx.font="14px sans-serif";
        ctx.fillText(`${classes[item.class_id] || "Object"}${ids?` #${item.id}`:""}`,box[0],Math.max(15,box[1]-4));
      }
      // Render newly entered tracks during the latter half of a sample gap.
      if (ratio > 0.55) for (const item of b.objects) {
        if (a.objects.some(existing => existing.id === item.id)) continue;
        ctx.strokeStyle=item.class_id===0?"#42d392":"#ffad52";
        ctx.lineWidth=2;
        ctx.strokeRect(item.box[0],item.box[1],item.box[2]-item.box[0],item.box[3]-item.box[1]);
        ctx.fillStyle=ctx.strokeStyle;ctx.font="14px sans-serif";
        ctx.fillText(`${classes[item.class_id] || "Object"}${ids?` #${item.id}`:""}`,item.box[0],Math.max(15,item.box[1]-4));
      }
    }
    function tick(_now:number, metadata:VideoFrameCallbackMetadata) {
      if(stopped || !player)return;
      draw(metadata.mediaTime);
      callback=player.requestVideoFrameCallback(tick);
    }
    const redraw=()=>draw(player.currentTime);
    callback=player.requestVideoFrameCallback(tick);
    player.addEventListener("seeked",redraw);
    redraw();
    return ()=>{stopped=true;player.cancelVideoFrameCallback(callback);player.removeEventListener("seeked",redraw);};
  },[tracks,annotations,ids]);

  return <article className="viewerTile"><div className="streamFrame">
    <div style={{position:"relative",lineHeight:0}}>
      <video ref={video} src={camera.source_url} controls autoPlay muted loop playsInline
        style={{width:"100%",height:"auto",minHeight:0,display:"block",objectFit:"contain"}}
        onError={()=>setMessage("Video could not load. Check that the local backend is running.")}/>
      <canvas ref={canvas} style={{position:"absolute",inset:0,width:"100%",height:"100%",pointerEvents:"none"}}/>
    </div>
    <div className="viewerControls">
      <label><input type="checkbox" checked={annotations} onChange={e=>setAnnotations(e.target.checked)}/> Show AI annotations</label>
      <label><input type="checkbox" checked={ids} onChange={e=>setIds(e.target.checked)}/> Track IDs</label>
    </div>
    <small role="status">{message}</small>
    {tracks?<div className="analyticsOverlay"><b>DETECTIONS AT PLAYBACK POSITION</b><span>People {counts.people}</span><span>Vehicles {counts.vehicles}</span><em>{tracks.mode ?? `Source timestamps at ${tracks.fps/tracks.step} analysed FPS.`}</em></div>:null}
    </div><footer><strong>{camera.name}</strong><span className="statusTag">RECORDED</span></footer></article>;
}
