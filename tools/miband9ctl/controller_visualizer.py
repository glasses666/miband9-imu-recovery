#!/usr/bin/env python3
"""Local browser visualizer for Mi Band 9 ControllerState.

Runs the same calibrated controller core as the Windows receiver path, but serves
an Apple-ish browser HUD so the mapping/gate/recenter behavior is visible before
opening a game.
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from controller_state_server import DEFAULT_CALIBRATION, DEFAULT_PACKAGE, iter_live_samples, load_calibration
from miband9ctl.controller import ControllerMapper
from miband9ctl.controller_stream import frame_for_state, samples_from_probe_json


@dataclass
class VisualizerState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    status: str = "starting"
    error: str = ""
    mode: str = "live"
    started_wall: float = field(default_factory=time.time)
    last_frame_wall: float = 0.0
    frames: int = 0
    latest: dict[str, Any] | None = None
    history: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=420))
    request_recenter: bool = False
    calibration_name: str = ""
    tuning: dict[str, float] = field(default_factory=dict)
    pending_tuning: dict[str, float] | None = None

    def add_frame(self, frame: dict[str, Any], raw_state: dict[str, Any]) -> None:
        item = {**frame, **raw_state, "wall_ms": int(time.time() * 1000)}
        with self.lock:
            self.latest = item
            self.history.append(item)
            self.frames += 1
            self.last_frame_wall = time.time()
            self.status = "live"

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            latest = dict(self.latest) if self.latest else None
            history = list(self.history)
            age_ms = int((time.time() - self.started_wall) * 1000)
            last_age = None if not self.last_frame_wall else int((time.time() - self.last_frame_wall) * 1000)
            return {
                "status": self.status,
                "error": self.error,
                "mode": self.mode,
                "age_ms": age_ms,
                "last_packet_age_ms": last_age,
                "frames": self.frames,
                "latest": latest,
                "history": history,
                "calibration_name": self.calibration_name,
                "tuning": dict(self.tuning),
            }


def _load_probe_samples(path: Path):
    with path.expanduser().open(encoding="utf-8") as fh:
        return list(samples_from_probe_json(json.load(fh)))


def run_capture(args: argparse.Namespace, shared: VisualizerState) -> None:
    try:
        calibration = load_calibration(args.calibration)
        shared.calibration_name = calibration.name or args.calibration.name
        mapper = ControllerMapper(
            calibration,
            tilt_full_scale_deg=args.tilt_full_scale_deg,
            yaw_rate_full_scale=args.yaw_rate_full_scale,
            pitch_rate_full_scale=args.pitch_rate_full_scale,
            deadzone=args.deadzone,
            smoothing_alpha=args.smoothing_alpha,
            response_curve=args.response_curve,
            tilt_x_sign=-1.0 if args.invert_tilt_x else 1.0,
            tilt_y_sign=-1.0 if args.invert_tilt_y else 1.0,
            gyro_x_sign=-1.0 if args.invert_gyro_x else 1.0,
            gyro_y_sign=-1.0 if args.invert_gyro_y else 1.0,
        )
        with shared.lock:
            shared.tuning = mapper.tuning_snapshot()
        if args.probe_json:
            shared.mode = "probe"
            samples = _load_probe_samples(args.probe_json)
            seq = 0
            while True:
                for sample in samples:
                    with shared.lock:
                        pending = shared.pending_tuning
                        shared.pending_tuning = None
                        do_recenter = shared.request_recenter
                        shared.request_recenter = False
                    if pending:
                        mapper.set_tuning(**pending)
                        with shared.lock:
                            shared.tuning = mapper.tuning_snapshot()
                    if do_recenter:
                        mapper.recenter_current()
                    state = mapper.update(sample, now_ms=int(time.time() * 1000))
                    frame = frame_for_state(seq=seq, state=state)
                    shared.add_frame(frame, state.as_dict())
                    seq += 1
                    time.sleep(1.0 / max(1.0, args.rate_hz))
                if not args.loop_probe:
                    break
        else:
            shared.mode = "live"
            seq = 0
            for sample in iter_live_samples(args):
                with shared.lock:
                    pending = shared.pending_tuning
                    shared.pending_tuning = None
                    do_recenter = shared.request_recenter
                    shared.request_recenter = False
                if pending:
                    mapper.set_tuning(**pending)
                    with shared.lock:
                        shared.tuning = mapper.tuning_snapshot()
                if do_recenter:
                    mapper.recenter_current()
                state = mapper.update(sample, now_ms=int(time.time() * 1000))
                frame = frame_for_state(seq=seq, state=state)
                shared.add_frame(frame, state.as_dict())
                seq += 1
        with shared.lock:
            shared.status = "complete" if shared.frames else "no_frames"
    except Exception as exc:  # noqa: BLE001 - surface the exact UI failure.
        with shared.lock:
            shared.status = "error"
            shared.error = f"{exc.__class__.__name__}: {exc}"


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mi Band 9 Controller Calibration HUD</title>
<style>
:root{--bg:#05070c;--panel:rgba(15,22,34,.84);--panel2:rgba(8,12,20,.76);--line:rgba(136,166,214,.22);--ink:#f6f9ff;--muted:#93a4bd;--blue:#74b8ff;--green:#63f2a0;--red:#ff5d78;--amber:#ffd166;--purple:#b99cff}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 18% -12%,#253e68 0,#09101d 40%,#020409 100%);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text",Inter,Arial,sans-serif}.wrap{padding:18px;display:grid;grid-template-columns:1fr .95fr;gap:14px}.card{border:1px solid var(--line);background:linear-gradient(180deg,var(--panel),var(--panel2));backdrop-filter:blur(18px);border-radius:28px;box-shadow:0 24px 90px rgba(0,0,0,.35);padding:16px}.hero{grid-column:1/-1;display:flex;align-items:flex-end;justify-content:space-between;gap:16px}.title{font-size:32px;font-weight:900;letter-spacing:-.055em}.sub{color:var(--muted);margin-top:4px}.pills{display:flex;gap:8px;flex-wrap:wrap}.pill{padding:8px 11px;border-radius:999px;background:#101827;border:1px solid var(--line);font-weight:800;color:#dce8ff}.live{background:var(--green);color:#04100a}.wait{background:var(--amber);color:#170f03}.err{background:var(--red);color:#fff}.stale{background:#3b2230;color:#ffd7df}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.stick{aspect-ratio:1;border-radius:50%;background:radial-gradient(circle at 50% 50%,rgba(116,184,255,.12),rgba(5,7,12,.75));border:1px solid var(--line);position:relative;overflow:hidden}.stick:before,.stick:after{content:"";position:absolute;background:rgba(255,255,255,.1)}.stick:before{left:50%;top:0;width:1px;height:100%}.stick:after{top:50%;left:0;height:1px;width:100%}.dot{position:absolute;width:34px;height:34px;border-radius:50%;background:radial-gradient(circle,#fff,var(--blue));box-shadow:0 0 35px rgba(116,184,255,.85);transform:translate(-50%,-50%);left:50%;top:50%}.label{display:flex;align-items:center;justify-content:space-between;margin:10px 4px 0;color:var(--muted);font-weight:750}.value{font-variant-numeric:tabular-nums;color:#fff}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:14px}.metric{background:rgba(255,255,255,.055);border:1px solid var(--line);border-radius:18px;padding:10px}.metric b{display:block;font-size:20px}.metric span{color:var(--muted);font-size:12px}.meter{height:12px;background:rgba(255,255,255,.08);border-radius:999px;overflow:hidden;border:1px solid var(--line)}.meter i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--green),var(--amber),var(--red));border-radius:999px}.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.btn{appearance:none;border:1px solid var(--line);background:linear-gradient(180deg,rgba(116,184,255,.22),rgba(116,184,255,.08));color:var(--ink);border-radius:16px;padding:10px 13px;font-weight:850;cursor:pointer}.btn.primary{background:linear-gradient(180deg,rgba(99,242,160,.32),rgba(99,242,160,.1))}.clawReadout{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}.clawReadout span{padding:7px 10px;border-radius:999px;background:rgba(116,184,255,.1);border:1px solid var(--line);color:#dce8ff;font-weight:800}.band{height:360px;display:grid;place-items:center}.band canvas{width:100%;height:100%}.chart{width:100%;height:250px}pre{margin:10px 0 0;white-space:pre-wrap;word-break:break-word;color:#cfe0ff;max-height:250px;overflow:auto}.panelTitle{font-size:16px;font-weight:900;margin-bottom:10px}.hint{color:var(--muted);margin-top:6px}.controls{display:grid;grid-template-columns:1fr 1fr;gap:12px}.control{background:rgba(255,255,255,.055);border:1px solid var(--line);border-radius:18px;padding:12px}.control label{display:flex;justify-content:space-between;gap:10px;color:#dce8ff;font-weight:800}.control small{display:block;color:var(--muted);margin:4px 0 8px}.control input[type=range]{width:100%;accent-color:var(--blue)}.toggles{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.toggle{display:flex;align-items:center;gap:8px;background:rgba(255,255,255,.055);border:1px solid var(--line);border-radius:14px;padding:9px;color:#dce8ff;font-weight:760}.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;color:var(--muted)}.sw{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}@media(max-width:900px){.wrap{grid-template-columns:1fr}.hero{align-items:flex-start;flex-direction:column}.controls{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body><div class="wrap">
<section class="card hero"><div><div class="title">Mi Band 9 Dragon Claw HUD</div><div class="sub">Motion Channel 优先：Xbox 双摇杆只是兼容层；姿态、相对 yaw、掌面和 gesture 才是爪控本体。</div></div><div class="pills"><span id="status" class="pill wait">starting</span><span id="fps" class="pill">0 fps</span><span id="frames" class="pill">0 frames</span><span id="age" class="pill">age</span><span id="mode" class="pill">mode</span></div></section>
<section class="card"><div class="grid"><div><div id="ls" class="stick"><i class="dot"></i></div><div class="label"><span>LEFT · tilt</span><span id="lv" class="value">0,0</span></div></div><div><div id="rs" class="stick"><i class="dot"></i></div><div class="label"><span>RIGHT · gyro</span><span id="rv" class="value">0,0</span></div></div></div><div class="metrics"><div class="metric"><b id="gate">off</b><span>motion gate</span></div><div class="metric"><b id="pitch">0°</b><span>pitch</span></div><div class="metric"><b id="roll">0°</b><span>roll</span></div><div class="metric"><b id="age2">—</b><span>last sample</span></div><div class="metric"><b id="gesture">idle</b><span>gesture</span></div><div class="metric"><b id="conf">0%</b><span>confidence</span></div><div class="metric"><b id="palm">—</b><span>palm</span></div><div class="metric"><b id="yaw">0°</b><span>relative yaw</span></div></div><div style="margin-top:12px"><div class="label"><span>motion-channel intensity</span><span id="motionText" class="value">0%</span></div><div class="meter"><i id="motion"></i></div></div><div class="btns"><button class="btn primary" onclick="recenter()">Set current pose as neutral</button><button class="btn" onclick="preset('soft')">Soft</button><button class="btn" onclick="preset('sharp')">Sharp</button><button class="btn" onclick="togglePause()" id="pause">Pause view</button></div><div class="hint">校准顺序：手腕放到你觉得“正中”的握持姿势 → 点绿色按钮 → 小幅倾斜看左摇杆 → 再调下面灵敏度/死区。</div></section>
<section class="card"><div class="panelTitle">Motion Channel · Dragon Claw Pose</div><div class="clawReadout"><span id="intent">idle</span><span id="quat">quat —</span></div><div class="band"><canvas id="band"></canvas></div><div class="hint">蓝线=爪掌法线，绿线=前向，红线=横轴；爪尖张合由 motion intensity 程序化驱动，不假装读到了手指。</div></section>
<section class="card"><div class="panelTitle">Live Fine Calibration</div><div class="controls">
<div class="control"><label>Tilt full scale <span id="tilt_full_scale_deg_v"></span></label><small>越小越灵敏；先试 22°–35°。</small><input id="tilt_full_scale_deg" type="range" min="8" max="60" step="1"></div>
<div class="control"><label>Yaw gyro scale <span id="yaw_rate_full_scale_v"></span></label><small>越小右摇杆越猛。</small><input id="yaw_rate_full_scale" type="range" min="0.15" max="3" step="0.05"></div>
<div class="control"><label>Pitch gyro scale <span id="pitch_rate_full_scale_v"></span></label><small>右摇杆上下灵敏度。</small><input id="pitch_rate_full_scale" type="range" min="0.15" max="3" step="0.05"></div>
<div class="control"><label>Deadzone <span id="deadzone_v"></span></label><small>中位漂移就加大；反应迟钝就减小。</small><input id="deadzone" type="range" min="0" max="0.3" step="0.005"></div>
<div class="control"><label>Smoothing <span id="smoothing_alpha_v"></span></label><small>越小越稳但慢；越大越跟手。</small><input id="smoothing_alpha" type="range" min="0.05" max="1" step="0.01"></div>
<div class="control"><label>Response curve <span id="response_curve_v"></span></label><small>&gt;1 中心更细，&lt;1 起步更敏。</small><input id="response_curve" type="range" min="0.5" max="2.4" step="0.05"></div>
</div><div class="toggles"><label class="toggle"><input id="tilt_x_sign" type="checkbox"> invert tilt X</label><label class="toggle"><input id="tilt_y_sign" type="checkbox"> invert tilt Y</label><label class="toggle"><input id="gyro_x_sign" type="checkbox"> invert gyro X</label><label class="toggle"><input id="gyro_y_sign" type="checkbox"> invert gyro Y</label></div><div class="legend"><span><i class="sw" style="background:#ff5d78"></i>lx</span><span><i class="sw" style="background:#63f2a0"></i>ly</span><span><i class="sw" style="background:#74b8ff"></i>rx</span><span><i class="sw" style="background:#b99cff"></i>ry</span></div></section>
<section class="card"><b>Axis History</b><canvas class="chart" id="chart"></canvas></section>
<section class="card"><b>Raw</b><pre id="raw">waiting…</pre></section>
</div>
<script>
let state=null,lastFrames=0,lastFpsT=performance.now(),paused=false,pose={pitch:0,roll:0,yaw:0},hydrated=false,timer=null;const $=id=>document.getElementById(id);const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));const fmt=(v,d=2)=>(Number(v)||0).toFixed(d);const tunKeys=['tilt_full_scale_deg','yaw_rate_full_scale','pitch_rate_full_scale','deadzone','smoothing_alpha','response_curve'];
function setDot(id,x,y){let e=$(id),d=e.querySelector('.dot');d.style.left=(50+clamp(x,-1,1)*42)+'%';d.style.top=(50-clamp(y,-1,1)*42)+'%'}
function values(){let o={};tunKeys.forEach(k=>o[k]=Number($(k).value));['tilt_x_sign','tilt_y_sign','gyro_x_sign','gyro_y_sign'].forEach(k=>o[k]=$(k).checked?-1:1);return o}
function labelVals(){tunKeys.forEach(k=>{$(k+'_v').textContent=Number($(k).value).toFixed(k==='tilt_full_scale_deg'?0:2)})}
function hydrate(t){if(hydrated||!t)return;Object.entries(t).forEach(([k,v])=>{if($(k)&&$(k).type==='range')$(k).value=v;if($(k)&&$(k).type==='checkbox')$(k).checked=Number(v)<0});labelVals();hydrated=true}
async function pushTuning(){labelVals();clearTimeout(timer);timer=setTimeout(async()=>{await fetch('/api/tuning',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values())}).catch(()=>{})},70)}
addEventListener('load',()=>{tunKeys.forEach(k=>$(k).addEventListener('input',pushTuning));['tilt_x_sign','tilt_y_sign','gyro_x_sign','gyro_y_sign'].forEach(k=>$(k).addEventListener('change',pushTuning))});
async function poll(){try{let r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});state=await r.json();hydrate(state.tuning);if(!paused)render()}catch(e){$('status').textContent='api error';$('status').className='pill err'}setTimeout(poll,33)}
async function recenter(){await fetch('/api/recenter',{method:'POST'}).catch(()=>{})}
function preset(name){if(name==='soft'){tilt_full_scale_deg.value=38;yaw_rate_full_scale.value=1.6;pitch_rate_full_scale.value=1.6;deadzone.value=.08;smoothing_alpha.value=.24;response_curve.value=1.35}else{tilt_full_scale_deg.value=22;yaw_rate_full_scale.value=.75;pitch_rate_full_scale.value=.75;deadzone.value=.04;smoothing_alpha.value=.55;response_curve.value=.95}pushTuning()}
function togglePause(){paused=!paused;$('pause').textContent=paused?'Resume view':'Pause view'}
function render(){let l=state.latest||{},mo=l.motion||{},age=state.last_packet_age_ms;let fresh=age===null||age<1000;let live=state.status==='live'&&fresh;$('status').textContent=(fresh?state.status:'stale')+(l.gate?' · GATED':'');$('status').className='pill '+(state.status==='error'?'err':(live?'live':(fresh?'wait':'stale')));$('mode').textContent=state.mode+' · '+(state.calibration_name||'cal');$('frames').textContent=(state.frames||0)+' frames';$('age').textContent=age===null?'age —':age+'ms';$('age2').textContent=age===null?'—':(age<1000?age+'ms':(age/1000).toFixed(1)+'s');let now=performance.now();if(now-lastFpsT>500){$('fps').textContent=Math.round(((state.frames-lastFrames)*1000)/(now-lastFpsT))+' fps';lastFrames=state.frames;lastFpsT=now}setDot('ls',l.lx||0,l.ly||0);setDot('rs',l.rx||0,l.ry||0);$('lv').textContent=`${fmt(l.lx)}, ${fmt(l.ly)}`;$('rv').textContent=`${fmt(l.rx)}, ${fmt(l.ry)}`;$('gate').textContent=l.gate?'ON':'off';$('gate').style.color=l.gate?'var(--amber)':'var(--green)';$('pitch').textContent=fmt((mo.pitch_rad??l.pitch_rad??0)*57.2958,1)+'°';$('roll').textContent=fmt((mo.roll_rad??l.roll_rad??0)*57.2958,1)+'°';$('yaw').textContent=fmt((mo.yaw_rad||0)*57.2958,1)+'°';$('gesture').textContent=mo.gesture||'idle';$('conf').textContent=Math.round((mo.confidence||0)*100)+'%';$('palm').textContent=mo.palm||'—';$('intent').textContent=(mo.gesture||'idle')+' · '+Math.round((mo.intensity||0)*100)+'%';let q=mo.quat||{};$('quat').textContent=`q ${fmt(q.w,2)}, ${fmt(q.x,2)}, ${fmt(q.y,2)}, ${fmt(q.z,2)}`;let m=clamp((mo.intensity??((Math.abs(l.lx||0)+Math.abs(l.ly||0)+Math.abs(l.rx||0)+Math.abs(l.ry||0))/2))+(l.gate?.15:0),0,1);$('motion').style.width=(m*100)+'%';$('motionText').textContent=Math.round(m*100)+'%';$('raw').textContent=JSON.stringify({status:state.status,error:state.error,last_packet_age_ms:state.last_packet_age_ms,tuning:state.tuning,latest:l},null,2);drawBand(l);drawChart(state.history||[])}
function drawBand(l){let c=$('band'),ctx=c.getContext('2d'),dpr=devicePixelRatio||1,w=c.clientWidth*dpr,h=c.clientHeight*dpr;if(c.width!==w){c.width=w;c.height=h}ctx.clearRect(0,0,w,h);ctx.save();ctx.scale(dpr,dpr);let W=c.clientWidth,H=c.clientHeight;let mo=l.motion||{};pose.pitch+=(((mo.pitch_rad??l.pitch_rad??0)-pose.pitch)*.25);pose.roll+=(((mo.roll_rad??l.roll_rad??0)-pose.roll)*.25);pose.yaw+=(((mo.yaw_rad??pose.yaw)-pose.yaw)*.25);function rot(p){let x=p.x,y=p.y,z=p.z,cp=Math.cos(pose.pitch),sp=Math.sin(pose.pitch),cr=Math.cos(pose.roll),sr=Math.sin(pose.roll),cy=Math.cos(pose.yaw),sy=Math.sin(pose.yaw);let y1=y*cp-z*sp,z1=y*sp+z*cp;y=y1;z=z1;let x2=x*cr+z*sr,z2=-x*sr+z*cr;x=x2;z=z2;let x3=x*cy-y*sy,y3=x*sy+y*cy;return{x:x3,y:y3,z}}function pr(p){let dist=520,s=dist/(dist+p.z);return{x:W/2+p.x*s,y:H/2-p.y*s}}function poly(arr,fill,stroke='rgba(245,248,255,.55)'){ctx.beginPath();let p=pr(rot(arr[0]));ctx.moveTo(p.x,p.y);for(let i=1;i<arr.length;i++){p=pr(rot(arr[i]));ctx.lineTo(p.x,p.y)}ctx.closePath();ctx.fillStyle=fill;ctx.strokeStyle=stroke;ctx.lineWidth=2;ctx.fill();ctx.stroke()}let hw=54,hl=142,ht=14;let top=[{x:-hw,y:-hl,z:ht},{x:hw,y:-hl,z:ht},{x:hw,y:hl,z:ht},{x:-hw,y:hl,z:ht}],body=[{x:-hw,y:-hl,z:-ht},{x:hw,y:-hl,z:-ht},{x:hw,y:hl,z:-ht},{x:-hw,y:hl,z:-ht}];poly(body,'rgba(18,24,36,.88)');poly(top,l.gate?'rgba(255,209,102,.32)':'rgba(30,48,78,.96)','rgba(116,184,255,.8)');poly([{x:-32,y:-104,z:ht+2},{x:32,y:-104,z:ht+2},{x:34,y:104,z:ht+2},{x:-34,y:104,z:ht+2}], 'rgba(4,8,14,.92)','rgba(99,242,160,.55)');function line(a,b,col,t){let pa=pr(rot(a)),pb=pr(rot(b));ctx.strokeStyle=col;ctx.lineWidth=t;ctx.beginPath();ctx.moveTo(pa.x,pa.y);ctx.lineTo(pb.x,pb.y);ctx.stroke()}line({x:-110,y:-hl,z:ht+8},{x:110,y:-hl,z:ht+8},'#ff5d78',5);line({x:0,y:-210,z:ht+8},{x:0,y:210,z:ht+8},'#63f2a0',4);line({x:0,y:0,z:ht+8},{x:0,y:0,z:110},'#74b8ff',4);let spread=24+clamp((l.motion?.intensity||0),0,1)*54;for(let i=-2;i<=2;i++){let base=i*22;line({x:base,y:hl-12,z:ht+6},{x:base*1.35,y:hl+88+spread*.45,z:ht+18+spread*.18},'#dce8ff',3.5);let tip=pr(rot({x:base*1.35,y:hl+88+spread*.45,z:ht+18+spread*.18}));ctx.fillStyle=i==0?'#74b8ff':'#b99cff';ctx.beginPath();ctx.arc(tip.x,tip.y,4.5,0,Math.PI*2);ctx.fill()}ctx.fillStyle='rgba(116,184,255,.12)';ctx.beginPath();ctx.arc(W/2,H/2,80+Math.abs(l.lx||0)*80+Math.abs(l.ly||0)*80,0,Math.PI*2);ctx.fill();ctx.restore()}
function drawChart(hist){let c=$('chart'),ctx=c.getContext('2d'),dpr=devicePixelRatio||1,w=c.clientWidth*dpr,h=c.clientHeight*dpr;if(c.width!==w){c.width=w;c.height=h}ctx.clearRect(0,0,w,h);ctx.save();ctx.scale(dpr,dpr);let W=c.clientWidth,H=c.clientHeight;ctx.strokeStyle='rgba(255,255,255,.08)';for(let i=1;i<4;i++){ctx.beginPath();ctx.moveTo(0,H*i/4);ctx.lineTo(W,H*i/4);ctx.stroke()}let data=hist.slice(-220);if(data.length<2){ctx.restore();return}let keys=['lx','ly','rx','ry'],cols=['#ff5d78','#63f2a0','#74b8ff','#b99cff'];keys.forEach((k,ki)=>{ctx.strokeStyle=cols[ki];ctx.lineWidth=2;ctx.beginPath();data.forEach((p,i)=>{let x=i/(data.length-1)*W,y=H/2-(Number(p[k])||0)*(H*.42);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y)});ctx.stroke()});ctx.restore()}
poll();
</script></body></html>'''


def make_handler(shared: VisualizerState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                body = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/state":
                body = json.dumps(shared.snapshot(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/recenter":
                with shared.lock:
                    shared.request_recenter = True
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            if path == "/api/tuning":
                length = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                    allowed = {
                        "tilt_full_scale_deg",
                        "yaw_rate_full_scale",
                        "pitch_rate_full_scale",
                        "deadzone",
                        "smoothing_alpha",
                        "response_curve",
                        "tilt_x_sign",
                        "tilt_y_sign",
                        "gyro_x_sign",
                        "gyro_y_sign",
                    }
                    pending = {k: float(v) for k, v in payload.items() if k in allowed}
                except Exception as exc:  # noqa: BLE001 - return useful local UI error.
                    body = json.dumps({"error": f"{exc.__class__.__name__}: {exc}"}).encode("utf-8")
                    self.send_response(HTTPStatus.BAD_REQUEST)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                with shared.lock:
                    shared.pending_tuning = pending
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    return Handler


def run(args: argparse.Namespace) -> int:
    shared = VisualizerState()
    capture = threading.Thread(target=run_capture, args=(args, shared), daemon=True)
    capture.start()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(shared))
    print(json.dumps({"status": "visualizer_listening", "url": f"http://127.0.0.1:{args.port}/", "mode": "probe" if args.probe_json else "live"}, ensure_ascii=False), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        httpd.server_close()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18770)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--probe-json", type=Path, default=None, help="Replay a sport_xms_probe.json instead of live Android data")
    parser.add_argument("--loop-probe", action="store_true")
    parser.add_argument("--rate-hz", type=float, default=100.0)
    parser.add_argument("--tilt-full-scale-deg", type=float, default=30.0)
    parser.add_argument("--yaw-rate-full-scale", type=float, default=1.0)
    parser.add_argument("--pitch-rate-full-scale", type=float, default=1.0)
    parser.add_argument("--deadzone", type=float, default=0.05)
    parser.add_argument("--smoothing-alpha", type=float, default=0.34)
    parser.add_argument("--response-curve", type=float, default=1.0)
    parser.add_argument("--invert-tilt-x", action="store_true")
    parser.add_argument("--invert-tilt-y", action="store_true")
    parser.add_argument("--invert-gyro-x", action="store_true")
    parser.add_argument("--invert-gyro-y", action="store_true")
    parser.add_argument("--serial", default="")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--duration-ms", type=int, default=3600000)
    parser.add_argument("--sport-type", type=int, default=812)
    parser.add_argument("--did", default="")
    parser.add_argument("--adb-timeout", type=int, default=20)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
