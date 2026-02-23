#!/usr/bin/env python3
"""Video → GIF v5 · 双击即用 · 浏览器GUI"""
import sys,os,subprocess,platform

def _ci(m):
    try:__import__(m);return True
    except ImportError:return False

def install():
    d={'PIL':'Pillow','numpy':'numpy'}
    m=[p for mod,p in d.items() if not _ci(mod)]
    if m:
        print(f"\n  安装依赖: {', '.join(m)} ...")
        for p in m:
            subprocess.check_call([sys.executable,'-m','pip','install',p,'-q'],
                                  stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
        print("  完成!\n")
install()

import json,time,shutil,tempfile,threading,webbrowser,re,urllib.request,http.server,socketserver,zipfile
from io import BytesIO
import base64,numpy as np
from PIL import Image

SCRIPT_DIR=os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR=os.path.join(SCRIPT_DIR,'_ffmpeg')

def find_ffmpeg():
    if shutil.which('ffmpeg'):return shutil.which('ffmpeg')
    for d in [FFMPEG_DIR,SCRIPT_DIR]:
        p=os.path.join(d,'ffmpeg'+('.exe' if os.name=='nt' else ''))
        if os.path.isfile(p):return p
    try:import imageio_ffmpeg;return imageio_ffmpeg.get_ffmpeg_exe()
    except:pass
    return None

def download_ffmpeg():
    ff=find_ffmpeg()
    if ff:return ff
    if os.name!='nt':
        print("  请安装ffmpeg: sudo apt install ffmpeg / brew install ffmpeg")
        return None
    print("\n  未检测到ffmpeg,正在自动下载(约70MB)...")
    os.makedirs(FFMPEG_DIR,exist_ok=True)
    url="https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    try:
        zp=os.path.join(FFMPEG_DIR,'ff.zip')
        _p=[0]
        def cb(bn,bs,ts):
            d=bn*bs
            if ts>0:
                p=min(100,d*100//ts)
                if p>=_p[0]+10:_p[0]=p;print(f"  {p}%")
        urllib.request.urlretrieve(url,zp,cb)
        print("  解压...")
        with zipfile.ZipFile(zp,'r') as z:
            for n in z.namelist():
                if n.endswith('ffmpeg.exe') and '/bin/' in n:
                    t=os.path.join(FFMPEG_DIR,'ffmpeg.exe')
                    with open(t,'wb') as f:f.write(z.read(n))
                    # Also extract ffprobe
                    pn=n.replace('ffmpeg.exe','ffprobe.exe')
                    if pn in z.namelist():
                        with open(os.path.join(FFMPEG_DIR,'ffprobe.exe'),'wb') as f:f.write(z.read(pn))
                    os.remove(zp);print(f"  已保存: {t}");return t
        os.remove(zp)
    except Exception as e:
        print(f"  下载失败: {e}")
        print("  请手动下载ffmpeg放入脚本同目录_ffmpeg文件夹")
    return None

# ══════════════════════════════════════════════
def get_video_info(path,ffmpeg):
    if not ffmpeg:return{'width':0,'height':0,'fps':30,'duration':0,'size':os.path.getsize(path),'error':'no ffmpeg'}
    # try ffprobe first
    fpb=ffmpeg.replace('ffmpeg','ffprobe')
    if not os.path.isfile(fpb):fpb=shutil.which('ffprobe')
    try:
        if fpb:
            r=subprocess.run([fpb,'-v','quiet','-print_format','json','-show_format','-show_streams',path],
                            capture_output=True,text=True,timeout=30,encoding='utf-8',errors='replace')
            if r.returncode==0:
                data=json.loads(r.stdout)
                for s in data.get('streams',[]):
                    if s.get('codec_type')=='video':
                        w,h=int(s.get('width',0)),int(s.get('height',0))
                        dur=float(data.get('format',{}).get('duration',0))
                        fs=s.get('r_frame_rate','30/1')
                        fps=eval(fs) if '/' in fs else float(fs)
                        return{'width':w,'height':h,'fps':round(fps,2),'duration':dur,'size':os.path.getsize(path)}
        # fallback: ffmpeg -i
        r=subprocess.run([ffmpeg,'-i',path],capture_output=True,text=True,timeout=30,encoding='utf-8',errors='replace')
        out=(r.stderr or '')+(r.stdout or '')
        dm=re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)',out)
        dur=int(dm[1])*3600+int(dm[2])*60+int(dm[3])+int(dm[4])/100 if dm else 0
        rm=re.search(r'(\d{2,5})x(\d{2,5})',out)
        w,h=(int(rm[1]),int(rm[2])) if rm else (0,0)
        fm=re.search(r'(\d+(?:\.\d+)?)\s*fps',out)
        fps=float(fm[1]) if fm else 30
        return{'width':w,'height':h,'fps':round(fps,2),'duration':dur,'size':os.path.getsize(path)}
    except:pass
    return{'width':0,'height':0,'fps':30,'duration':0,'size':os.path.getsize(path)}

def extract_frames(vpath,ffmpeg,fps,start,end,width):
    if not ffmpeg:raise RuntimeError("ffmpeg 未找到。请将 ffmpeg.exe 放入脚本同目录的 _ffmpeg 文件夹，或安装到系统 PATH")
    vi=get_video_info(vpath,ffmpeg)
    vw,vh=vi['width'] or 640,vi['height'] or 480
    sc=width/vw;oh=int(vh*sc);oh+=oh%2;ow=width;ow+=ow%2
    cmd=[ffmpeg,'-y','-ss',str(start),'-t',str(end-start),'-i',vpath,
         '-vf',f'fps={fps},scale={ow}:{oh}','-pix_fmt','rgb24','-f','rawvideo','pipe:1']
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    raw,_=proc.communicate(timeout=300)
    fsz=ow*oh*3;n=len(raw)//fsz
    return [np.frombuffer(raw[i*fsz:(i+1)*fsz],dtype=np.uint8).reshape((oh,ow,3)).copy() for i in range(n)],ow,oh

def apply_strategy(total,strategy,manual=''):
    k=[True]*total
    if strategy=='odd':
        for i in range(total):
            if(i+1)%2==1:k[i]=False
    elif strategy=='even':
        for i in range(total):
            if(i+1)%2==0:k[i]=False
    elif strategy=='every_n':
        # manual contains N
        try:n=int(manual)
        except:n=3
        for i in range(total):
            if(i+1)%n==0:k[i]=False
    elif strategy=='keep_n':
        try:n=int(manual)
        except:n=3
        for i in range(total):
            if(i+1)%n!=1:k[i]=False
    elif strategy=='manual':
        rm=set()
        for p in manual.split(','):
            p=p.strip()
            if '-' in p:
                try:a,b=p.split('-',1);rm.update(range(int(a),int(b)+1))
                except:pass
            elif p.isdigit():rm.add(int(p))
        for i in range(total):
            if(i+1) in rm:k[i]=False
    return k

def gen_gif(frames,kept_mask,fps,out_path,ffmpeg,max_mb=0,colors=256):
    kf=[f for f,k in zip(frames,kept_mask) if k]
    if not kf:return None,"没有保留帧"
    fs=None
    if ffmpeg:fs=_gf(kf,fps,out_path,ffmpeg,max_mb)
    if fs is None:fs=_gp(kf,fps,out_path,max_mb,colors)
    return fs,None

def _gf(frames,fps,out,ffmpeg,max_mb):
    td=tempfile.mkdtemp(prefix='vgif_')
    try:
        for i,f in enumerate(frames):Image.fromarray(f).save(os.path.join(td,f'f_{i:06d}.png'))
        inp,pal=os.path.join(td,'f_%06d.png'),os.path.join(td,'p.png')
        if subprocess.run([ffmpeg,'-y','-framerate',str(fps),'-i',inp,'-vf','palettegen=max_colors=256:stats_mode=diff',pal],capture_output=True,timeout=120).returncode!=0:return None
        if subprocess.run([ffmpeg,'-y','-framerate',str(fps),'-i',inp,'-i',pal,'-lavfi','paletteuse=dither=sierra2_4a','-loop','0',out],capture_output=True,timeout=180).returncode!=0:return None
        fs=os.path.getsize(out)
        if max_mb>0 and fs>max_mb*1048576:
            for c in[128,64,32]:
                subprocess.run([ffmpeg,'-y','-framerate',str(fps),'-i',inp,'-vf',f'palettegen=max_colors={c}:stats_mode=diff',pal],capture_output=True,timeout=120)
                subprocess.run([ffmpeg,'-y','-framerate',str(fps),'-i',inp,'-i',pal,'-lavfi','paletteuse=dither=sierra2_4a','-loop','0',out],capture_output=True,timeout=180)
                fs=os.path.getsize(out)
                if fs<=max_mb*1048576:break
        return fs
    except:return None
    finally:shutil.rmtree(td,ignore_errors=True)

def _gp(frames,fps,out,max_mb,colors):
    dl=int(1000/fps)
    def build(nc,sc=1.0):
        pf=[]
        for f in frames:
            img=Image.fromarray(f)
            if sc<1:img=img.resize((int(img.width*sc),int(img.height*sc)),Image.LANCZOS)
            pf.append(img.quantize(colors=nc,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.FLOYDSTEINBERG))
        pf[0].save(out,save_all=True,append_images=pf[1:],duration=dl,loop=0,optimize=True)
        return os.path.getsize(out)
    fs=build(colors)
    if max_mb>0:
        mx=max_mb*1048576;nc=colors;sc=1.0
        for _ in range(5):
            if fs<=mx:break
            r=mx/fs
            if r<0.5:nc=max(16,int(nc*0.5));sc*=0.85
            elif r<0.8:nc=max(16,int(nc*0.7));sc*=0.95
            else:nc=max(16,int(nc*0.85))
            fs=build(nc,sc)
    return fs

def fthmb(frame,w=100,h=75):
    buf=BytesIO();Image.fromarray(frame).resize((w,h),Image.LANCZOS).save(buf,format='JPEG',quality=55)
    return base64.b64encode(buf.getvalue()).decode()

# ══════════════════════════════════════════════
HTML=r'''<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video → GIF</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600&display=swap');
:root{
  --bg:#0f1123;--card:#161832;--card2:#1c1f3f;--border:#2a2d52;--border2:#353868;
  --gold:#c9a96e;--gold2:#dbbf8a;--gold-dim:rgba(201,169,110,.15);
  --text:#e8e6e1;--dim:#7a7d9e;--dim2:#50537a;
  --green:#5cb885;--red:#d95c5c;--radius:8px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans SC',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:14px}
.app{max-width:880px;margin:0 auto;padding:20px 16px 40px}
.hdr{text-align:center;padding:20px 0 24px;border-bottom:1px solid var(--border)}
.hdr h1{font-size:1.5rem;font-weight:600;color:var(--gold);letter-spacing:2px}
.hdr p{color:var(--dim);font-size:.78rem;margin-top:4px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;margin-top:16px}
.ct{font-size:.78rem;font-weight:500;color:var(--gold);margin-bottom:14px;padding-left:10px;border-left:3px solid var(--gold)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
label{font-size:.75rem;color:var(--dim);display:block;margin-bottom:4px}
input[type=number],select{width:100%;background:var(--card2);border:1px solid var(--border);border-radius:6px;padding:9px 12px;color:var(--text);font-size:.85rem;outline:none;transition:.2s}
input[type=number]:focus,select:focus{border-color:var(--gold)}
select option{background:var(--card)}
/* Range slider */
.slider-row{display:flex;align-items:center;gap:10px;margin-top:4px}
.slider-row input[type=range]{flex:1;-webkit-appearance:none;height:4px;background:var(--border);border-radius:2px;outline:none}
.slider-row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;background:var(--gold);border-radius:50%;cursor:pointer;box-shadow:0 0 6px rgba(201,169,110,.4)}
.slider-val{min-width:44px;text-align:right;font-size:.82rem;color:var(--gold);font-weight:500}
/* Time range slider */
.time-slider-wrap{position:relative;height:36px;margin:10px 0 4px;user-select:none}
.time-track{position:absolute;top:16px;left:0;right:0;height:4px;background:var(--border);border-radius:2px}
.time-range-fill{position:absolute;top:16px;height:4px;background:var(--gold);border-radius:2px}
.time-thumb{position:absolute;top:8px;width:18px;height:18px;background:var(--gold);border-radius:50%;cursor:pointer;
  transform:translateX(-9px);box-shadow:0 0 8px rgba(201,169,110,.5);z-index:2;transition:box-shadow .2s}
.time-thumb:hover{box-shadow:0 0 14px rgba(201,169,110,.7)}
.time-labels{display:flex;justify-content:space-between;font-size:.72rem;color:var(--dim)}
.time-labels span{font-weight:500;color:var(--gold2)}
/* Estimate bar */
.est{background:var(--card2);border:1px solid var(--border);border-radius:6px;padding:10px 14px;margin-top:14px;
  display:flex;justify-content:space-between;align-items:center;gap:12px}
.est-item{text-align:center;flex:1}
.est-item .ev{font-size:1rem;font-weight:600;color:var(--gold)}
.est-item .el{font-size:.62rem;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}
/* Strategy */
.strat-row{display:flex;gap:6px;flex-wrap:wrap}
.strat-chip{background:var(--card2);border:1px solid var(--border);border-radius:20px;padding:7px 14px;
  font-size:.75rem;cursor:pointer;transition:.2s;color:var(--dim);white-space:nowrap}
.strat-chip:hover{border-color:var(--gold);color:var(--text)}
.strat-chip.a{border-color:var(--gold);color:var(--gold);background:var(--gold-dim)}
.strat-extra{margin-top:10px;display:none}
.strat-extra input{width:100%;background:var(--card2);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--text);font-size:.82rem;outline:none}
.strat-extra input:focus{border-color:var(--gold)}
.strat-extra .hint{font-size:.65rem;color:var(--dim2);margin-top:3px}
/* Buttons */
.btn{padding:11px 24px;border:none;border-radius:6px;font-size:.85rem;cursor:pointer;transition:.2s;font-weight:500}
.btn-gold{background:var(--gold);color:#1a1a2e}
.btn-gold:hover{background:var(--gold2);box-shadow:0 4px 16px rgba(201,169,110,.3)}
.btn-gold:disabled{opacity:.35;cursor:not-allowed;box-shadow:none}
.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--dim)}
.btn-ghost:hover{border-color:var(--gold);color:var(--text)}
.btn-row{display:flex;gap:10px;margin-top:14px}
/* Progress */
.prog{height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:10px;display:none}
.prog-fill{height:100%;background:var(--gold);width:100%;animation:pulse 1.5s infinite}
.prog-txt{font-size:.72rem;color:var(--dim);text-align:center;margin-top:4px;display:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
/* Frame strip */
.fstrip{display:flex;gap:3px;overflow-x:auto;padding:8px 0;scrollbar-width:thin}
.fstrip::-webkit-scrollbar{height:4px}
.fstrip::-webkit-scrollbar-thumb{background:var(--gold);border-radius:2px}
.ft{flex-shrink:0;width:72px;height:54px;border-radius:4px;overflow:hidden;border:2px solid transparent;position:relative;cursor:pointer;transition:.15s}
.ft img{width:100%;height:100%;object-fit:cover}
.ft .fn{position:absolute;bottom:1px;left:1px;background:rgba(0,0,0,.7);color:#fff;font-size:.48rem;padding:0 3px;border-radius:2px}
.ft.k{border-color:var(--green)}
.ft.r{border-color:var(--red);opacity:.25}
.ft.r::after{content:'×';position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--red);font-size:.9rem;font-weight:700}
.ft:hover{transform:scale(1.06);z-index:2}
/* Stats */
.sts{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}
.st{background:var(--card2);border-radius:6px;padding:7px;text-align:center}
.st .v{font-size:.95rem;font-weight:600}.st .l{font-size:.58rem;color:var(--dim);text-transform:uppercase;margin-top:1px}
.st.g .v{color:var(--green)}.st.rd .v{color:var(--red)}.st.gd .v{color:var(--gold)}
/* Upload */
.uz{border:2px dashed var(--border);border-radius:var(--radius);padding:36px 20px;text-align:center;cursor:pointer;transition:.2s}
.uz:hover{border-color:var(--gold);background:var(--gold-dim)}
.uz .ico{font-size:2.2rem;margin-bottom:6px;opacity:.5}
.uz .tx{color:var(--dim);font-size:.82rem}.uz .ht{color:var(--dim2);font-size:.68rem;margin-top:3px}
#fi{display:none}
.vw{display:none;border-radius:6px;overflow:hidden;background:#000;margin-top:10px}
.vw video{width:100%;max-height:260px;display:block}
.vi{display:none;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}
.vc{background:var(--card2);border-radius:6px;padding:7px;text-align:center}
.vc .vl{font-size:.58rem;color:var(--dim);text-transform:uppercase;margin-bottom:2px}
.vc .vv{font-size:.82rem;font-weight:500}
.msg{margin-top:8px;font-size:.78rem;color:var(--red);display:none}
/* Output */
.oz{display:none;margin-top:16px}
.gp{text-align:center;margin-top:10px}
.gp img{max-width:100%;max-height:340px;border-radius:6px;border:1px solid var(--border)}
.dl{display:inline-block;margin-top:10px;background:var(--gold);color:#1a1a2e;padding:10px 28px;border-radius:6px;text-decoration:none;font-weight:500;transition:.2s}
.dl:hover{background:var(--gold2)}
@media(max-width:600px){.row{grid-template-columns:1fr}.sts{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body>
<div class="app">
<div class="hdr"><h1>VIDEO → GIF</h1><p>视频转 GIF · 帧级控制</p></div>

<div class="card">
<div class="ct">视频源</div>
<div class="uz" id="uz" onclick="$('fi').click()">
<div class="ico">🎬</div><div class="tx">拖拽视频到此处，或点击选择</div><div class="ht">MP4 / AVI / MOV / MKV / WebM</div>
</div>
<input type="file" id="fi" accept="video/*">
<div class="vw" id="vw"><video id="ve" controls></video></div>
<div class="vi" id="vi">
<div class="vc"><div class="vl">时长</div><div class="vv" id="vd">--</div></div>
<div class="vc"><div class="vl">分辨率</div><div class="vv" id="vr">--</div></div>
<div class="vc"><div class="vl">大小</div><div class="vv" id="vs">--</div></div>
</div></div>

<div class="card" id="paramCard" style="display:none">
<div class="ct">截取范围</div>
<div class="time-slider-wrap" id="tsWrap">
  <div class="time-track"></div>
  <div class="time-range-fill" id="tsFill"></div>
  <div class="time-thumb" id="tsL" style="left:0%"></div>
  <div class="time-thumb" id="tsR" style="left:100%"></div>
</div>
<div class="time-labels"><span id="tlL">0.0s</span><span id="tlM">时长: --</span><span id="tlR">--</span></div>

<div style="margin-top:16px"><label>帧率 (FPS)</label>
<div class="slider-row"><input type="range" id="fps" min="1" max="30" value="10" oninput="updEst()"><span class="slider-val" id="fv">10</span></div></div>

<div style="margin-top:10px"><label>输出宽度 (px)</label>
<div class="slider-row"><input type="range" id="wd" min="120" max="1280" value="480" step="10" oninput="updEst()"><span class="slider-val" id="wv">480</span></div></div>

<div class="row" style="margin-top:10px">
<div><label>最大文件 MB (0=不限)</label><input type="number" id="ms" value="0" min="0" step="0.5"></div>
<div><label>颜色数</label><select id="cs"><option value="256">256</option><option value="128">128</option><option value="64">64</option></select></div>
</div>

<!-- Live estimate -->
<div class="est" id="estBar">
  <div class="est-item"><div class="ev" id="estFrames">--</div><div class="el">预估帧数</div></div>
  <div class="est-item"><div class="ev" id="estDur">--</div><div class="el">预估时长</div></div>
  <div class="est-item"><div class="ev" id="estSize">--</div><div class="el">预估大小</div></div>
</div>
</div>

<div class="card" id="stratCard" style="display:none">
<div class="ct">帧删除策略</div>
<div class="strat-row" id="sr"></div>
<div class="strat-extra" id="se">
<input type="text" id="seV" placeholder="" oninput="updEst()">
<div class="hint" id="seH"></div>
</div>
</div>

<div class="card" id="actCard" style="display:none">
<div class="btn-row">
<button class="btn btn-gold" id="eb" onclick="doExtract()">提取帧画面</button>
<button class="btn btn-ghost" id="rb" onclick="doReset()" disabled>重置</button>
</div>
<div class="prog" id="p1"><div class="prog-fill" id="p1f"></div></div>
<div class="prog-txt" id="p1t"></div>
<div class="msg" id="msg"></div>
</div>

<div class="card" id="fc" style="display:none">
<div class="ct">帧预览 <span style="font-size:.65rem;color:var(--dim);margin-left:6px;font-weight:300">点击切换保留/删除</span></div>
<div class="fstrip" id="fstrip"></div>
<div class="sts">
<div class="st gd"><div class="v" id="s0">0</div><div class="l">总帧数</div></div>
<div class="st g"><div class="v" id="s1">0</div><div class="l">保留</div></div>
<div class="st rd"><div class="v" id="s2">0</div><div class="l">删除</div></div>
<div class="st"><div class="v" id="s3">--</div><div class="l">预估大小</div></div>
</div>
<div class="btn-row"><button class="btn btn-gold" style="flex:1" id="gb" onclick="doGen()">生成 GIF ›</button></div>
<div class="prog" id="p2"><div class="prog-fill" id="p2f"></div></div>
<div class="prog-txt" id="p2t"></div>
</div>

<div class="card oz" id="oz">
<div class="ct">生成结果</div>
<div class="sts" id="os" style="grid-template-columns:repeat(3,1fr)"></div>
<div class="gp" id="gp"></div>
</div>
</div>

<script>
const $=id=>document.getElementById(id);
let vpath='',vdur=0,frames=[],strat='none',stratParam='';

// Strategies
const SS=[
  ['none','保留全部',null,null],
  ['odd','删奇数帧',null,null],
  ['even','删偶数帧',null,null],
  ['every_n','每N帧删1','输入N值 (如3=每3帧删1帧)','3'],
  ['keep_n','每N帧留1','输入N值 (如3=每3帧只留1帧)','3'],
  ['manual','手动指定','输入帧号, 如: 1,3,5,10-15','']
];
const sr=$('sr');
SS.forEach(([k,nm,ph,dv])=>{
  const c=document.createElement('span');c.className='strat-chip'+(k==='none'?' a':'');c.dataset.s=k;
  c.textContent=nm;c.onclick=()=>setSt(k,ph,dv);sr.appendChild(c);
});
function setSt(s,ph,dv){
  strat=s;
  document.querySelectorAll('.strat-chip').forEach(c=>c.classList.toggle('a',c.dataset.s===s));
  const se=$('se');
  if(ph){se.style.display='block';$('seV').placeholder=ph;$('seH').textContent=ph;if(dv)$('seV').value=dv}
  else{se.style.display='none'}
  stratParam=$('seV').value;
  updEst();if(frames.length>0)applySt();
}

// Upload
const uz=$('uz'),fi=$('fi');
uz.ondragover=e=>{e.preventDefault();uz.style.borderColor='var(--gold)'};
uz.ondragleave=()=>{uz.style.borderColor=''};
uz.ondrop=e=>{e.preventDefault();uz.style.borderColor='';if(e.dataTransfer.files.length)handleFile(e.dataTransfer.files[0])};
fi.onchange=e=>{if(e.target.files.length)handleFile(e.target.files[0])};

function handleFile(file){
  const fd=new FormData();fd.append('video',file);showMsg('上传中...');
  fetch('/api/upload',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.error){showMsg('错误: '+d.error);return}
    vpath=d.path;vdur=d.duration;
    $('vd').textContent=d.duration.toFixed(1)+'s';$('vr').textContent=d.width+'×'+d.height;$('vs').textContent=fmtSz(d.size);
    $('vi').style.display='grid';$('ve').src='/api/video?t='+Date.now();$('vw').style.display='block';uz.style.display='none';
    // Init time slider
    tStart=0;tEnd=vdur;initTimeSlider();updEst();
    $('paramCard').style.display='block';$('stratCard').style.display='block';$('actCard').style.display='block';
    hideMsg();
  }).catch(e=>showMsg('上传失败: '+e));
}

// ── Time Range Slider ──
let tStart=0,tEnd=0,dragging=null;
function initTimeSlider(){
  const wrap=$('tsWrap'),tl=$('tsL'),tr=$('tsR');
  tEnd=vdur;renderTime();
  function pct(e){const r=wrap.getBoundingClientRect();return Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))}
  function onDown(which){return e=>{e.preventDefault();dragging=which;
    const mv=e2=>{const p=pct(e2.touches?e2.touches[0]:e2);
      if(dragging==='L'){tStart=Math.min(p*vdur,tEnd-0.1)}else{tEnd=Math.max(p*vdur,tStart+0.1)}
      renderTime();updEst()};
    const up=()=>{dragging=null;document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);
      document.removeEventListener('touchmove',mv);document.removeEventListener('touchend',up)};
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);
    document.addEventListener('touchmove',mv,{passive:false});document.addEventListener('touchend',up)}}
  tl.onmousedown=onDown('L');tl.ontouchstart=onDown('L');
  tr.onmousedown=onDown('R');tr.ontouchstart=onDown('R');
}
function renderTime(){
  if(!vdur)return;
  const lp=tStart/vdur*100,rp=tEnd/vdur*100;
  $('tsL').style.left=lp+'%';$('tsR').style.left=rp+'%';
  $('tsFill').style.left=lp+'%';$('tsFill').style.width=(rp-lp)+'%';
  $('tlL').textContent=tStart.toFixed(1)+'s';$('tlR').textContent=tEnd.toFixed(1)+'s';
  $('tlM').textContent='选取: '+(tEnd-tStart).toFixed(1)+'s';
}

// ── Live Estimate ──
function updEst(){
  const fps=+$('fps').value, w=+$('wd').value;
  $('fv').textContent=fps;$('wv').textContent=w;
  const dur=Math.max(0,tEnd-tStart);
  let totalF=Math.max(1,Math.round(dur*fps));
  // Apply strategy estimate
  stratParam=$('seV')?$('seV').value:'';
  let kept=totalF;
  if(strat==='odd')kept=Math.floor(totalF/2);
  else if(strat==='even')kept=Math.ceil(totalF/2);
  else if(strat==='every_n'){const n=parseInt(stratParam)||3;kept=totalF-Math.floor(totalF/n)}
  else if(strat==='keep_n'){const n=parseInt(stratParam)||3;kept=Math.ceil(totalF/n)}
  kept=Math.max(1,kept);
  $('estFrames').textContent=kept;
  $('estDur').textContent=(kept/fps).toFixed(1)+'s';
  const estKB=kept*w*0.04;
  $('estSize').textContent=estKB>1024?(estKB/1024).toFixed(1)+' MB':Math.round(estKB)+' KB';
}

// ── Extract ──
function doExtract(){
  const p={path:vpath,fps:+$('fps').value,start:tStart,end:tEnd,width:+$('wd').value};
  showProg('p1','p1t','提取中...');$('eb').disabled=true;
  fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
  .then(r=>r.json()).then(d=>{
    hideProg('p1','p1t');$('eb').disabled=false;
    if(d.error){showMsg('错误: '+d.error);return}
    frames=d.frames.map((t,i)=>({thumb:t,kept:true}));renderFr();applySt();
    $('fc').style.display='block';$('rb').disabled=false;
    $('fc').scrollIntoView({behavior:'smooth'});
  }).catch(e=>{hideProg('p1','p1t');showMsg('失败: '+e)});
}

function renderFr(){
  const s=$('fstrip');s.innerHTML='';
  frames.forEach((f,i)=>{const d=document.createElement('div');d.className='ft '+(f.kept?'k':'r');
  d.onclick=()=>{frames[i].kept=!frames[i].kept;d.className='ft '+(frames[i].kept?'k':'r');updSt()};
  d.innerHTML=`<img src="data:image/jpeg;base64,${f.thumb}"><div class="fn">${i+1}</div>`;s.appendChild(d)});updSt();
}
function applySt(){
  stratParam=$('seV')?$('seV').value:'';
  const mp=strat==='every_n'||strat==='keep_n'?stratParam:(strat==='manual'?stratParam:'');
  fetch('/api/strategy',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({total:frames.length,strategy:strat,manual:mp})})
  .then(r=>r.json()).then(d=>{
    d.kept.forEach((k,i)=>{if(i<frames.length)frames[i].kept=k});
    document.querySelectorAll('.ft').forEach((t,i)=>{if(i<frames.length)t.className='ft '+(frames[i].kept?'k':'r')});updSt();
  });
}
function updSt(){
  const t=frames.length,k=frames.filter(f=>f.kept).length;
  $('s0').textContent=t;$('s1').textContent=k;$('s2').textContent=t-k;
  const w=+$('wd').value,est=k*w*0.04;
  $('s3').textContent=est>1024?(est/1024).toFixed(1)+' MB':Math.round(est)+' KB';
}
function doReset(){strat='none';document.querySelectorAll('.strat-chip').forEach(c=>c.classList.toggle('a',c.dataset.s==='none'));
$('se').style.display='none';frames.forEach(f=>f.kept=true);document.querySelectorAll('.ft').forEach(t=>t.className='ft k');updSt();updEst()}

// ── Generate ──
function doGen(){
  const ki=frames.map((f,i)=>f.kept?i:-1).filter(i=>i>=0);
  if(!ki.length){showMsg('请至少保留一帧');return}
  showProg('p2','p2t','生成中...');$('gb').disabled=true;
  fetch('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:vpath,kept:ki,fps:+$('fps').value,max_size:+$('ms').value,colors:+$('cs').value})})
  .then(r=>r.json()).then(d=>{
    hideProg('p2','p2t');$('gb').disabled=false;
    if(d.error){showMsg('错误: '+d.error);return}
    $('oz').style.display='block';
    $('os').innerHTML=`<div class="st g"><div class="v">${d.frame_count}</div><div class="l">帧数</div></div>
      <div class="st gd"><div class="v">${fmtSz(d.file_size)}</div><div class="l">大小</div></div>
      <div class="st"><div class="v">${d.duration}s</div><div class="l">时长</div></div>`;
    $('gp').innerHTML=`<img src="/api/output?t=${Date.now()}"><br><a class="dl" href="/api/download">下载 GIF ›</a>`;
    $('oz').scrollIntoView({behavior:'smooth'});
  }).catch(e=>{hideProg('p2','p2t');showMsg('失败: '+e)});
}

function fmtSz(b){if(b<1024)return b+' B';if(b<1048576)return(b/1024).toFixed(1)+' KB';return(b/1048576).toFixed(2)+' MB'}
function showMsg(m){const e=$('msg');e.textContent=m;e.style.display='block';setTimeout(()=>e.style.display='none',6000)}
function hideMsg(){$('msg').style.display='none'}
function showProg(a,c,m){$(a).style.display='block';$(c).style.display='block';$(c).textContent=m}
function hideProg(a,c){$(a).style.display='none';$(c).style.display='none'}
</script></body></html>'''

# ══════════════════════════════════════════════
class State:
    video_path='';frames=[];output_path='';ffmpeg=None
S=State()

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def _json(self,d):
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps(d,ensure_ascii=False).encode())
    def _file(self,p,ct):
        if not os.path.isfile(p):self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(os.path.getsize(p)));self.end_headers()
        with open(p,'rb') as f:shutil.copyfileobj(f,self.wfile)
    def do_GET(self):
        p=self.path.split('?')[0]
        if p in('/',''):
            self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.end_headers()
            self.wfile.write(HTML.encode())
        elif p=='/api/video' and S.video_path:
            ext=os.path.splitext(S.video_path)[1].lower()
            ct={'.mp4':'video/mp4','.avi':'video/x-msvideo','.mov':'video/quicktime','.mkv':'video/x-matroska','.webm':'video/webm'}.get(ext,'video/mp4')
            self._file(S.video_path,ct)
        elif p=='/api/output' and S.output_path:self._file(S.output_path,'image/gif')
        elif p=='/api/download' and S.output_path and os.path.isfile(S.output_path):
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Disposition',f'attachment; filename="{os.path.basename(S.output_path)}"')
            self.send_header('Content-Length',str(os.path.getsize(S.output_path)));self.end_headers()
            with open(S.output_path,'rb') as f:shutil.copyfileobj(f,self.wfile)
        else:self.send_error(404)
    def do_POST(self):
        p=self.path.split('?')[0];cl=int(self.headers.get('Content-Length',0))
        if p=='/api/upload':
            ct=self.headers.get('Content-Type','');bd=ct.split('boundary=')[1] if 'boundary=' in ct else ''
            body=self.rfile.read(cl);td=tempfile.mkdtemp(prefix='vgif_');fn='video.mp4'
            for part in body.split(b'--'+bd.encode()):
                if b'filename="' in part:
                    m=re.search(rb'filename="([^"]+)"',part)
                    if m:fn=m.group(1).decode('utf-8',errors='replace')
                    idx=part.find(b'\r\n\r\n')
                    if idx>=0:
                        fd=part[idx+4:]
                        if fd.endswith(b'\r\n'):fd=fd[:-2]
                        sp=os.path.join(td,fn)
                        with open(sp,'wb') as f:f.write(fd)
                        S.video_path=sp;break
            if not S.video_path:self._json({'error':'上传失败'});return
            vi=get_video_info(S.video_path,S.ffmpeg)
            self._json({'path':S.video_path,'width':vi['width'],'height':vi['height'],'fps':vi['fps'],'duration':vi['duration'],'size':vi['size']})
        elif p=='/api/extract':
            d=json.loads(self.rfile.read(cl))
            try:
                S.frames,w,h=extract_frames(S.video_path,S.ffmpeg,d['fps'],d['start'],d['end'],d['width'])
                self._json({'frames':[fthmb(f) for f in S.frames],'width':w,'height':h})
            except Exception as e:self._json({'error':str(e)})
        elif p=='/api/strategy':
            d=json.loads(self.rfile.read(cl))
            self._json({'kept':apply_strategy(d['total'],d['strategy'],d.get('manual',''))})
        elif p=='/api/generate':
            d=json.loads(self.rfile.read(cl))
            try:
                ki=set(d['kept']);km=[(i in ki) for i in range(len(S.frames))]
                base=os.path.splitext(os.path.basename(S.video_path))[0]
                out=os.path.join(os.path.dirname(S.video_path),f'{base}.gif')
                fs,err=gen_gif(S.frames,km,d['fps'],out,S.ffmpeg,max_mb=d.get('max_size',0),colors=d.get('colors',256))
                if err:self._json({'error':err});return
                S.output_path=out;kc=sum(km)
                self._json({'file_size':fs,'frame_count':kc,'duration':f"{kc/d['fps']:.2f}",'path':out})
            except Exception as e:self._json({'error':str(e)})

def main():
    if os.name=='nt':
        try:import ctypes;ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11),7)
        except:pass
    print("\n\033[93m  VIDEO → GIF v5\033[0m\n")
    S.ffmpeg=find_ffmpeg()
    if not S.ffmpeg:S.ffmpeg=download_ffmpeg()
    if S.ffmpeg:print(f"  \033[92m✔\033[0m ffmpeg: {S.ffmpeg}")
    else:print("  \033[91m!\033[0m ffmpeg未找到。请将ffmpeg.exe放入脚本同目录 _ffmpeg 文件夹\n     下载: https://www.gyan.dev/ffmpeg/builds/");input("  按回车退出...");return
    port=8976
    for p in range(8976,9100):
        try:server=socketserver.TCPServer(('127.0.0.1',p),H);port=p;break
        except OSError:continue
    url=f'http://127.0.0.1:{port}'
    print(f"  \033[92m✔\033[0m {url}")
    print(f"  \033[93m>\033[0m 浏览器打开中... 关闭此窗口停止\n")
    threading.Timer(0.5,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:print("\n  已停止");server.shutdown()

if __name__=='__main__':main()
