#!/usr/bin/env python3
"""Browser-based live display for Mi Band 9 SportXms/Just Dance IMU.

Starts the hfimucli SportXms/812 capture through adb, streams matching
structured logcat messages by nonce, and serves a local dashboard that polls
latest packet state. This avoids macOS Tk rendering issues.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import socket
import subprocess
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

DEFAULT_PACKAGE = "nodomain.freeyourgadget.gadgetbridge.hfimucli"
HFIMU_RECEIVER_CLASS = "nodomain.freeyourgadget.gadgetbridge.externalevents.hfimu.HfImuCliReceiver"
LOG_FILTERS = ["MI_HFIMU_RESULT:I", "MI_HFIMU_STATE:I", "MI_HFIMU_ERROR:I", "*:S"]


@dataclass
class Packet:
    index: int = 0
    elapsed_ms: int = 0
    accel_samples: int = 0
    gyro_samples: int = 0
    hz: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0
    arx: float = 0.0
    ary: float = 0.0
    arz: float = 0.0
    grx: float = 0.0
    gry: float = 0.0
    grz: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    intensity: float = 0.0
    intensity01: float = 0.0
    samples: list[dict[str, float]] = field(default_factory=list)


class SharedState:
    def __init__(self, *, request_id: str, nonce: str, duration_ms: int, raw_log: str, calibration: Optional[dict[str, Any]] = None) -> None:
        self.lock = threading.Lock()
        self.request_id = request_id
        self.nonce = nonce
        self.duration_ms = duration_ms
        self.raw_log = raw_log
        self.calibration = calibration or {}
        self.status = "starting"
        self.device_info: dict[str, Any] = {}
        self.started = False
        self.complete = False
        self.failed = False
        self.error = ""
        self.packet_count = 0
        self.accel_samples = 0
        self.gyro_samples = 0
        self.max_intensity = 1.0
        self.latest: Optional[Packet] = None
        self.history: list[Packet] = []
        self.started_wall = time.time()
        self.last_packet_wall = 0.0

    def add_payload(self, payload: dict[str, Any]) -> None:
        msg = payload.get("message", "")
        with self.lock:
            if msg == "sensor_packet":
                packet = packet_from_payload(payload)
                self.max_intensity = max(self.max_intensity, packet.intensity, 1.0)
                packet.intensity01 = min(1.0, packet.intensity / self.max_intensity)
                self.latest = packet
                self.history.append(packet)
                if len(self.history) > 240:
                    self.history = self.history[-240:]
                self.packet_count += 1
                self.accel_samples += packet.accel_samples
                self.gyro_samples += packet.gyro_samples
                self.last_packet_wall = time.time()
                self.status = "live"
            elif msg == "device_info":
                self.device_info = {
                    "device_connected": str(payload.get("device_connected", "")),
                    "support_somatosensory": str(payload.get("support_somatosensory", "")),
                    "device_model": str(payload.get("device_model", "")),
                    "did_present": str(payload.get("did_present", "")),
                }
                self.status = "device_info"
            elif msg == "sport_started":
                self.started = True
                self.status = "sport_started"
            elif msg == "probe_complete":
                self.complete = True
                self.status = "complete"
            elif msg == "probe_failed":
                self.failed = True
                self.error = str(payload.get("reason", "probe_failed"))
                self.status = "failed"
            elif payload.get("status") == "error":
                self.failed = True
                self.error = str(payload.get("reason", payload.get("message", "error")))
                self.status = "error"

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            latest = asdict(self.latest) if self.latest else None
            history = [asdict(p) for p in self.history[-180:]]
            return {
                "request_id": self.request_id,
                "duration_ms": self.duration_ms,
                "raw_log": self.raw_log,
                "calibration": self.calibration,
                "status": self.status,
                "device_info": self.device_info,
                "started": self.started,
                "complete": self.complete,
                "failed": self.failed,
                "error": self.error,
                "packet_count": self.packet_count,
                "accel_samples": self.accel_samples,
                "gyro_samples": self.gyro_samples,
                "latest": latest,
                "history": history,
                "age_ms": int((time.time() - self.started_wall) * 1000),
                "last_packet_age_ms": None if self.last_packet_wall == 0 else int((time.time() - self.last_packet_wall) * 1000),
            }


def adb_prefix(serial: Optional[str]) -> list[str]:
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    return cmd


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def component_for_package(package: str) -> str:
    return f"{package}/{HFIMU_RECEIVER_CLASS}"


def action_for_package(package: str) -> str:
    return f"{package}.CLI"


def clear_logcat(serial: Optional[str]) -> None:
    run(adb_prefix(serial) + ["logcat", "-c"], timeout=15)


def start_logcat(serial: Optional[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        adb_prefix(serial) + ["logcat", "-v", "brief", *LOG_FILTERS],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )


def broadcast_probe(args: argparse.Namespace, request_id: str, nonce: str) -> subprocess.CompletedProcess[str]:
    cmd = adb_prefix(args.serial) + [
        "shell", "am", "broadcast",
        "--include-stopped-packages",
        "-n", component_for_package(args.package),
        "-a", action_for_package(args.package),
        "--es", "command", "sport-xms-probe",
        "--es", "request_id", request_id,
        "--es", "nonce", nonce,
        "--es", "capture_ms", str(max(500, args.duration_ms)),
        "--es", "xms_start", "true" if args.start else "false",
        "--es", "xms_sport_type", str(args.sport_type),
    ]
    if args.did:
        cmd += ["--es", "xms_did", args.did]
    return run(cmd, timeout=args.adb_timeout)


def extract_payload(line: str, nonce: str) -> Optional[dict[str, Any]]:
    if nonce not in line:
        return None
    start = line.find("{")
    end = line.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(line[start:end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def f(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def i(payload: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(str(payload.get(key, default)))
    except (TypeError, ValueError):
        return default


def mid(payload: dict[str, Any], prefix: str, axis: str) -> float:
    return (f(payload, f"{prefix}_{axis}_min") + f(payload, f"{prefix}_{axis}_max")) / 2.0


def rng(payload: dict[str, Any], prefix: str, axis: str) -> float:
    return f(payload, f"{prefix}_{axis}_max") - f(payload, f"{prefix}_{axis}_min")


def csv_floats(payload: dict[str, Any], key: str) -> list[float]:
    raw = str(payload.get(key, "") or "")
    values: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            pass
    return values


def csv_ints(payload: dict[str, Any], key: str) -> list[int]:
    raw = str(payload.get(key, "") or "")
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(float(part)))
        except ValueError:
            pass
    return values


def build_samples(payload: dict[str, Any]) -> list[dict[str, float]]:
    at = csv_ints(payload, "accel_t_values")
    ax = csv_floats(payload, "accel_x_values")
    ay = csv_floats(payload, "accel_y_values")
    az = csv_floats(payload, "accel_z_values")
    gx = csv_floats(payload, "gyro_x_values")
    gy = csv_floats(payload, "gyro_y_values")
    gz = csv_floats(payload, "gyro_z_values")
    n = min(len(ax), len(ay), len(az), len(gx), len(gy), len(gz))
    if at:
        n = min(n, len(at))
    samples: list[dict[str, float]] = []
    for idx in range(n):
        samples.append({
            "t": float(at[idx] if idx < len(at) else idx),
            "ax": ax[idx], "ay": ay[idx], "az": az[idx],
            "gx": gx[idx], "gy": gy[idx], "gz": gz[idx],
        })
    return samples


def packet_from_payload(payload: dict[str, Any]) -> Packet:
    n = i(payload, "accel_samples")
    first = i(payload, "first_accel_timestamp")
    last = i(payload, "last_accel_timestamp")
    hz = ((n - 1) * 1_000_000.0 / (last - first)) if n > 1 and last > first else 0.0
    ax, ay, az = mid(payload, "accel", "x"), mid(payload, "accel", "y"), mid(payload, "accel", "z")
    gx, gy, gz = mid(payload, "gyro", "x"), mid(payload, "gyro", "y"), mid(payload, "gyro", "z")
    arx, ary, arz = rng(payload, "accel", "x"), rng(payload, "accel", "y"), rng(payload, "accel", "z")
    grx, gry, grz = rng(payload, "gyro", "x"), rng(payload, "gyro", "y"), rng(payload, "gyro", "z")
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az))) if (ax or ay or az) else 0.0
    roll = math.degrees(math.atan2(ay, az)) if (ay or az) else 0.0
    intensity = math.sqrt(arx * arx + ary * ary + arz * arz) + 0.6 * math.sqrt(grx * grx + gry * gry + grz * grz)
    return Packet(
        index=i(payload, "packet_index"), elapsed_ms=i(payload, "elapsed_ms"),
        accel_samples=n, gyro_samples=i(payload, "gyro_samples"), hz=hz,
        ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
        arx=arx, ary=ary, arz=arz, grx=grx, gry=gry, grz=grz,
        pitch=pitch, roll=roll, intensity=intensity, samples=build_samples(payload),
    )


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Mi Band 9 Live 3D IMU</title>
<style>
:root{--bg:#03050a;--panel:#0b111b;--line:#24314a;--ink:#f5f8ff;--muted:#8ea0bd;--blue:#75b7ff;--green:#69f0a6;--red:#ff667f;--amber:#ffd166;--purple:#b99cff}*{box-sizing:border-box}body{margin:0;overflow:hidden;background:radial-gradient(circle at 20% 0%,#1a2440 0,#03050a 48%,#010204 100%);color:var(--ink);font:14px/1.4 -apple-system,BlinkMacSystemFont,"SF Pro Text",Arial,sans-serif}.shell{height:100vh;display:grid;grid-template-columns:1fr 390px;gap:14px;padding:14px}.card{background:rgba(11,17,27,.94);border:1px solid rgba(117,183,255,.18);border-radius:24px;box-shadow:0 25px 90px rgba(0,0,0,.42);padding:16px}.stage{position:relative;min-height:0}.title{font-size:27px;font-weight:900;letter-spacing:-.045em}.sub{color:var(--muted);margin-top:4px}.status{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.pill{border:1px solid var(--line);background:#101827;color:#d7e6ff;border-radius:999px;padding:7px 10px;font-weight:750}.live{background:var(--green);color:#04100a}.wait{background:var(--amber);color:#171004}canvas{width:100%;height:100%;display:block}.viz{height:calc(100vh - 164px);min-height:460px;margin-top:14px;border-radius:22px;border:1px solid rgba(255,255,255,.07);background:radial-gradient(circle at center,rgba(117,183,255,.16),rgba(0,0,0,.22) 54%,rgba(0,0,0,.4));overflow:hidden}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.metric{background:#101827;border:1px solid var(--line);border-radius:18px;padding:10px}.metric b{display:block;font-size:25px;letter-spacing:-.045em}.metric span{font-size:12px;color:var(--muted)}.big{font-size:30px;font-weight:900;color:var(--green);letter-spacing:-.04em}.readout{font:12px Menlo,monospace;color:#dbe8ff;white-space:pre-wrap;margin-top:10px}.chart{height:132px;margin-top:10px;border-radius:16px;background:#05070c;border:1px solid rgba(255,255,255,.07)}.legend{display:flex;gap:10px;color:var(--muted);font-size:12px;margin-top:8px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px}.note{color:var(--amber);font-size:13px;margin-top:8px}@media(max-width:960px){.shell{grid-template-columns:1fr}.side{display:none}}
</style>
</head>
<body>
<div class="shell">
<main class="card stage"><div class="title">Mi Band 9 100Hz IMU · Live Band Model</div><div class="sub">低延迟版：每包 10 个 sample 按 100Hz 消费；浏览器按屏幕刷新率绘制，积压会自动丢旧帧。</div><div class="status"><span id="livePill" class="pill wait">WAITING</span><span id="status" class="pill">status</span><span id="device" class="pill">device</span><span id="queue" class="pill">queue 0</span></div><div class="viz"><canvas id="cube"></canvas></div><div class="metrics"><div class="metric"><b id="packet">—</b><span>packet batch</span></div><div class="metric"><b id="hz">—</b><span>sample Hz</span></div><div class="metric"><b id="sampleRate">—</b><span>visual sample clock</span></div><div class="metric"><b id="motion">—</b><span>motion</span></div></div></main>
<aside class="card side"><div class="big" id="headline">等待数据…</div><div class="note">当前零位：平放桌面、屏幕朝上、短边朝 Mac 屏幕。pitch/roll 已扣零，yaw 是相对积分，会漂，不是绝对指南针。</div><div class="legend"><span><i class="dot" style="background:#ff667f"></i>X</span><span><i class="dot" style="background:#69f0a6"></i>Y</span><span><i class="dot" style="background:#75b7ff"></i>Z</span></div><div class="readout" id="readout"></div><canvas class="chart" id="accel"></canvas><canvas class="chart" id="gyro"></canvas><canvas class="chart" id="motionChart"></canvas></aside>
</div>
<script>
let state=null,lastPacket=0,sampleQ=[],sampleHist=[],cur=null,lastStep=performance.now();
let pose={pitch:0,roll:0,yaw:0},packetHz=0;
const $=id=>document.getElementById(id); const fmt=(n,d=1)=>(Number(n)||0).toFixed(d); const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function synthSamples(p){return [{t:performance.now(),ax:p.ax||0,ay:p.ay||0,az:p.az||0,gx:p.gx||0,gy:p.gy||0,gz:p.gz||0,_synthetic:true}]}
async function poll(){try{let r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'}); state=await r.json(); let p=state.latest; if(p&&p.index!==lastPacket){lastPacket=p.index; packetHz=p.hz||0; let samples=(p.samples&&p.samples.length)?p.samples:synthSamples(p); for(const s of samples){s.packet=p.index; sampleQ.push(s)} if(sampleQ.length>80) sampleQ=sampleQ.slice(-80);}}catch(e){$('status').textContent='api error'} setTimeout(poll,30)}
function consumeSample(now){if(sampleQ.length>24){sampleQ=sampleQ.slice(-10); lastStep=now-10} if(!cur&&sampleQ.length) cur=sampleQ.shift(); while(sampleQ.length && now-lastStep>=10){cur=sampleQ.shift(); lastStep+=10} if(now-lastStep>60) lastStep=now; if(cur){sampleHist.push(cur); if(sampleHist.length>360) sampleHist=sampleHist.slice(-360); let cal=(state&&state.calibration)||{}, gb=cal.gyro_bias||{}; let ax=cur.ax||0,ay=cur.ay||0,az=cur.az||0; let gx=(cur.gx||0)-Number(gb.x||0), gy=(cur.gy||0)-Number(gb.y||0), gz=(cur.gz||0)-Number(gb.z||0); cur.gxc=gx; cur.gyc=gy; cur.gzc=gz; let targetPitch=Math.atan2(-ax,Math.sqrt(ay*ay+az*az))-Number(cal.pitch_rad||0); let targetRoll=Math.atan2(ay,az)-Number(cal.roll_rad||0); pose.pitch=pose.pitch*.62+targetPitch*.38; pose.roll=pose.roll*.62+targetRoll*.38; pose.yaw+=gz*0.010;}}
function project(v,W,H){let dist=560,scale=dist/(dist+v.z);return{x:W/2+v.x*scale,y:H/2-v.y*scale,scale}}
function rot(v){let x=v.x,y=v.y,z=v.z;let cp=Math.cos(pose.pitch),sp=Math.sin(pose.pitch),cr=Math.cos(pose.roll),sr=Math.sin(pose.roll),cy=Math.cos(pose.yaw),sy=Math.sin(pose.yaw);let y1=y*cp-z*sp,z1=y*sp+z*cp;y=y1;z=z1;let x2=x*cr+z*sr,z2=-x*sr+z*cr;x=x2;z=z2;let x3=x*cy-y*sy,y3=x*sy+y*cy;return{x:x3,y:y3,z}}
function drawCube(now){consumeSample(now);let c=$('cube'),ctx=c.getContext('2d'),dpr=devicePixelRatio||1,w=c.clientWidth*dpr,h=c.clientHeight*dpr;if(c.width!==w){c.width=w;c.height=h}ctx.clearRect(0,0,w,h);ctx.save();ctx.scale(dpr,dpr);let W=c.clientWidth,H=c.clientHeight;ctx.strokeStyle='rgba(117,183,255,.08)';ctx.lineWidth=1;for(let x=0;x<W;x+=38){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}for(let y=0;y<H;y+=38){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}if(!cur){ctx.fillStyle='#ffd166';ctx.font='900 36px -apple-system';ctx.textAlign='center';ctx.fillText('WAITING FOR LIVE SAMPLES',W/2,H/2);ctx.restore();requestAnimationFrame(drawCube);return}
let intensity=clamp(Math.sqrt((cur.gxc||cur.gx||0)**2+(cur.gyc||cur.gy||0)**2+(cur.gzc||cur.gz||0)**2)*5 + Math.abs((cur.ax||0)-9.8)*.08,0,1);
// Draw a Mi Band-like slab instead of an abstract box.
// Local axes for the visual model:
// X = screen short-edge / width, shown as the Mac-facing reference direction in neutral pose.
// Y = screen long-edge / strap direction.
// Z = screen normal, positive out of the glass face.
let halfW=64, halfL=190, halfT=15;
let pts=[[-halfW,-halfL,-halfT],[halfW,-halfL,-halfT],[halfW,halfL,-halfT],[-halfW,halfL,-halfT],[-halfW,-halfL,halfT],[halfW,-halfL,halfT],[halfW,halfL,halfT],[-halfW,halfL,halfT]].map(([x,y,z])=>rot({x,y,z}));
let faces=[[0,1,2,3,'rgba(18,24,35,.92)'],[4,5,6,7,'rgba(20,28,43,.98)'],[0,1,5,4,'rgba(255,102,127,.38)'],[1,2,6,5,'rgba(105,240,166,.22)'],[2,3,7,6,'rgba(117,183,255,.22)'],[3,0,4,7,'rgba(255,209,102,.24)']];
faces.sort((a,b)=>a.slice(0,4).reduce((s,i)=>s+pts[i].z,0)-b.slice(0,4).reduce((s,i)=>s+pts[i].z,0));
function poly(indices,fill,stroke='rgba(245,248,255,.62)',lw=2){let pp=indices.map(i=>project(pts[i],W,H));ctx.beginPath();ctx.moveTo(pp[0].x,pp[0].y);for(let i=1;i<pp.length;i++)ctx.lineTo(pp[i].x,pp[i].y);ctx.closePath();ctx.fillStyle=fill;ctx.strokeStyle=stroke;ctx.lineWidth=lw;ctx.fill();ctx.stroke();return pp}
for(const f of faces){poly(f.slice(0,4),f[4])}
// Screen glass, inset on the top face.
let screenLocal=[[-44,-150,halfT+1],[44,-150,halfT+1],[44,150,halfT+1],[-44,150,halfT+1]];
let sp=screenLocal.map(([x,y,z])=>project(rot({x,y,z}),W,H));let grad=ctx.createLinearGradient(sp[0].x,sp[0].y,sp[2].x,sp[2].y);grad.addColorStop(0,'rgba(7,11,18,.98)');grad.addColorStop(.55,'rgba(25,42,70,.96)');grad.addColorStop(1,'rgba(6,8,12,.98)');ctx.beginPath();ctx.moveTo(sp[0].x,sp[0].y);for(let i=1;i<sp.length;i++)ctx.lineTo(sp[i].x,sp[i].y);ctx.closePath();ctx.fillStyle=grad;ctx.strokeStyle='rgba(122,184,255,.75)';ctx.lineWidth=3;ctx.fill();ctx.stroke();
// Screen highlight line and small home/reference mark.
let hp=[[-24,-112,halfT+2],[24,-112,halfT+2],[30,112,halfT+2],[-30,112,halfT+2]].map(([x,y,z])=>project(rot({x,y,z}),W,H));ctx.beginPath();ctx.moveTo(hp[0].x,hp[0].y);for(let i=1;i<hp.length;i++)ctx.lineTo(hp[i].x,hp[i].y);ctx.closePath();ctx.fillStyle='rgba(117,183,255,.10)';ctx.fill();
function line3(a,b,col,lw=4,label=''){let pa=project(rot(a),W,H),pb=project(rot(b),W,H);ctx.strokeStyle=col;ctx.lineWidth=lw;ctx.beginPath();ctx.moveTo(pa.x,pa.y);ctx.lineTo(pb.x,pb.y);ctx.stroke();if(label){ctx.fillStyle=col;ctx.font='900 17px -apple-system';ctx.fillText(label,pb.x+8,pb.y)}}
line3({x:-halfW-34,y:-halfL,z:halfT+6},{x:halfW+78,y:-halfL,z:halfT+6},'#ff667f',5,'短边→Mac / X');
line3({x:0,y:-halfL-42,z:halfT+8},{x:0,y:halfL+42,z:halfT+8},'#69f0a6',4,'长边 / strap');
line3({x:0,y:0,z:halfT+10},{x:0,y:0,z:halfT+96},'#75b7ff',4,'屏幕朝上 / Z');
// Strap ghost extensions, so the object reads as a band instead of a brick.
let strap1=[[-34,-halfL-170,-halfT*.6],[34,-halfL-170,-halfT*.6],[34,-halfL, -halfT*.6],[-34,-halfL,-halfT*.6]].map(([x,y,z])=>project(rot({x,y,z}),W,H));ctx.beginPath();ctx.moveTo(strap1[0].x,strap1[0].y);for(let i=1;i<strap1.length;i++)ctx.lineTo(strap1[i].x,strap1[i].y);ctx.closePath();ctx.fillStyle='rgba(64,76,96,.32)';ctx.fill();
let strap2=[[-34,halfL,-halfT*.6],[34,halfL,-halfT*.6],[34,halfL+170,-halfT*.6],[-34,halfL+170,-halfT*.6]].map(([x,y,z])=>project(rot({x,y,z}),W,H));ctx.beginPath();ctx.moveTo(strap2[0].x,strap2[0].y);for(let i=1;i<strap2.length;i++)ctx.lineTo(strap2[i].x,strap2[i].y);ctx.closePath();ctx.fillStyle='rgba(64,76,96,.32)';ctx.fill();
ctx.fillStyle='rgba(105,240,166,.12)';ctx.beginPath();ctx.arc(W/2,H/2,70+intensity*180,0,Math.PI*2);ctx.fill();ctx.restore();updateText(intensity);requestAnimationFrame(drawCube)}
function updateText(intensity){let live=state&&state.status==='live'&&state.last_packet_age_ms<1000;$('livePill').textContent=live?'LIVE':'WAITING';$('livePill').className='pill '+(live?'live':'wait');$('status').textContent=state?`${state.status} ${Math.round(state.age_ms/1000)}s`:'';$('device').textContent=state&&state.device_info?`connected=${state.device_info.device_connected} support=${state.device_info.support_somatosensory}`:'device';$('queue').textContent='queue '+sampleQ.length;$('packet').textContent=cur&&cur.packet?cur.packet:'—';$('hz').textContent=fmt(packetHz,1);$('sampleRate').textContent='100Hz data';$('motion').textContent=Math.round(intensity*100)+'%';if(cur){$('headline').textContent=`PACKET ${cur.packet||'—'} · SAMPLE ${fmt(packetHz,1)}Hz`; $('readout').textContent=`sample queue: ${sampleQ.length}\naccel: ${fmt(cur.ax,3)}, ${fmt(cur.ay,3)}, ${fmt(cur.az,3)}\ngyro raw: ${fmt(cur.gx,4)}, ${fmt(cur.gy,4)}, ${fmt(cur.gz,4)}\ngyro calibrated: ${fmt(cur.gxc??cur.gx,4)}, ${fmt(cur.gyc??cur.gy,4)}, ${fmt(cur.gzc??cur.gz,4)}\npitch/roll/relative yaw: ${fmt(pose.pitch*57.3,1)}, ${fmt(pose.roll*57.3,1)}, ${fmt(pose.yaw*57.3,1)}\ncalibration: ${state&&state.calibration&&state.calibration.name?state.calibration.name:'none'}\nraw log: ${state?state.raw_log:''}`; chart('accel',['ax','ay','az'],['#ff667f','#69f0a6','#75b7ff']); chart('gyro',['gx','gy','gz'],['#ff667f','#69f0a6','#75b7ff']); chart('motionChart',['motion'],['#69f0a6'],intensity)}}
function chart(id,fields,colors,motion){let c=$(id); if(!c) return;let ctx=c.getContext('2d'),dpr=devicePixelRatio||1,w=c.clientWidth*dpr,h=c.clientHeight*dpr;if(c.width!==w){c.width=w;c.height=h}ctx.clearRect(0,0,w,h);let hist=sampleHist.slice(-180).map(s=>({...s,motion:motion??0})); if(hist.length<2)return;let vals=[];hist.forEach(p=>fields.forEach(f=>vals.push(Number(p[f])||0)));let lo=Math.min(...vals),hi=Math.max(...vals),sp=hi-lo||1;ctx.strokeStyle='rgba(255,255,255,.08)';for(let i=1;i<4;i++){ctx.beginPath();ctx.moveTo(0,h*i/4);ctx.lineTo(w,h*i/4);ctx.stroke()}fields.forEach((f,k)=>{ctx.strokeStyle=colors[k];ctx.lineWidth=2*dpr;ctx.beginPath();hist.forEach((p,i)=>{let x=i/(hist.length-1)*w,y=h-((Number(p[f])||0)-lo)/sp*h;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()})}
poll(); requestAnimationFrame(drawCube);
</script>
</body></html>
"""


def logcat_reader(proc: subprocess.Popen[str], state: SharedState, raw_path: Path) -> None:
    with raw_path.open("a", encoding="utf-8") as raw:
        assert proc.stdout is not None
        for line in proc.stdout:
            raw.write(line)
            raw.flush()
            payload = extract_payload(line, state.nonce)
            if payload is not None:
                state.add_payload(payload)


def make_handler(state: SharedState) -> type[BaseHTTPRequestHandler]:
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
                body = json.dumps(state.snapshot(), ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
    return Handler


def choose_port(host: str, port: int) -> int:
    for candidate in range(port, port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise RuntimeError("no_free_port")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browser live Mi Band 9 SportXms/812 IMU dashboard")
    parser.add_argument("--serial")
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--duration-ms", type=int, default=600000)
    parser.add_argument("--sport-type", type=int, default=812)
    parser.add_argument("--did", default="")
    parser.add_argument("--start", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--adb-timeout", type=int, default=30)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--out", default="artifacts/sport_xms_probe/live_web")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--calibration", default="", help="Optional JSON calibration file for neutral pitch/roll and gyro bias")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.duration_ms = max(500, min(args.duration_ms, 600000))
    request_id = uuid.uuid4().hex[:12]
    nonce = uuid.uuid4().hex
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / f"live_web_sportxms_{time.strftime('%Y%m%d_%H%M%S')}.log"
    port = choose_port(args.host, args.port)
    url = f"http://{args.host}:{port}/"
    if args.dry_run:
        print(json.dumps({"url": url, "duration_ms": args.duration_ms, "sport_type": args.sport_type, "raw_log": str(raw_path), "did_present": bool(args.did)}, ensure_ascii=False, indent=2))
        return 0
    calibration = {}
    if args.calibration:
        with open(args.calibration, encoding="utf-8") as f:
            calibration = json.load(f)
    state = SharedState(request_id=request_id, nonce=nonce, duration_ms=args.duration_ms, raw_log=str(raw_path), calibration=calibration)
    clear_logcat(args.serial)
    logcat = start_logcat(args.serial)
    reader = threading.Thread(target=logcat_reader, args=(logcat, state, raw_path), daemon=True)
    reader.start()
    server = ThreadingHTTPServer((args.host, port), make_handler(state))
    sent = broadcast_probe(args, request_id, nonce)
    if sent.returncode != 0:
        state.failed = True
        state.status = "broadcast_failed"
        state.error = (sent.stderr or sent.stdout or "broadcast_failed").strip()
    print(f"READY {url} duration_ms={args.duration_ms} raw_log={raw_path}", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            logcat.terminate()
            logcat.wait(timeout=2)
        except Exception:
            try:
                logcat.kill()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
