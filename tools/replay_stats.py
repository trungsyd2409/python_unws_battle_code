"""
replay_stats.py - doc file .replay (tai tu web hoac tu unswbc run) va in thong ke tung team.

Can: Node.js (https://nodejs.org) va unswbc (pip install unswbc).
Cach dung:
    python tools/replay_stats.py replays/M399321.replay [nhieu file khac...]
    python tools/replay_stats.py M399321.replay --json out.json   # xuat toan bo event ra JSON

In ra cho moi team:
  - so dragon va con dai nhat theo thoi gian (moi 50 round)
  - so lan split + kich thuoc con, so lan sprint, so lan sonar
  - nguyen nhan chet (W=kelp, S=tu can, O=dam than khac, H=dam dau, A=khong co lenh / tu sat)
  - tu sat gan dong doi dai (dau hieu "nuoi" con chu luc)
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

KEY = 'function Pf(e){let t=Mf(e);return Nf(t,[...t.events].map(e=>Tf(e,t.formatVersion)))}'
NODE_RUNNER = r"""
const fs=require('fs');
const H={get:(t,p)=>{if(p===Symbol.toPrimitive)return()=>0;if(p==='length')return 0;return P;},apply:()=>P,construct:()=>P,has:()=>true};
const P=new Proxy(function(){},H);
for (const k of ['window','document','navigator','acquireVsCodeApi','HTMLElement','Element','Node','customElements','requestAnimationFrame','location','self','matchMedia','getComputedStyle','ResizeObserver','MutationObserver','localStorage']) if(!(k in globalThis)) globalThis[k]=P;
try{ eval(fs.readFileSync(process.argv[2],'utf8')); }catch(e){ if(!String(e).includes('__STOP__')) throw e; }
const b=fs.readFileSync(process.argv[3]);
const r=globalThis.__Pf(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));
fs.writeFileSync(process.argv[4],JSON.stringify({map:r.map,seed:String(r.seed),result:r.result,events:r.events},(k,v)=>typeof v==='bigint'?String(v):v));
"""


def decoder_dir():
    import unswbc
    vsix = os.path.join(os.path.dirname(unswbc.__file__), "replay-viewer.vsix")
    out = os.path.join(tempfile.gettempdir(), "unswbc_replay_decoder")
    js = os.path.join(out, "wv.js")
    if not os.path.exists(js):
        os.makedirs(out, exist_ok=True)
        with zipfile.ZipFile(vsix) as z:
            src = z.read("extension/dist/webview/webview.js").decode("utf8")
        if KEY not in src:
            sys.exit("phien ban replay viewer nay khac, can cap nhat KEY trong replay_stats.py")
        src = src.replace(KEY, KEY + ';globalThis.__Pf=Pf;throw new Error("__STOP__");')
        open(js, "w", encoding="utf8").write(src)
        open(os.path.join(out, "run.js"), "w").write(NODE_RUNNER)
    return out


def replay_to_json(path):
    node = shutil.which("node")
    if not node:
        sys.exit("can cai Node.js de doc replay (https://nodejs.org)")
    d = decoder_dir()
    out = os.path.join(d, "last.json")
    subprocess.run([node, os.path.join(d, "run.js"), os.path.join(d, "wv.js"), path, out], check=True)
    return json.load(open(out))


def simulate(data, callback=None):
    """Theo doi than tung dragon qua cac event. callback(round, event, team, bodies)."""
    team, bodies, nid = {}, {}, 0
    for line in data["map"].split("\n"):
        if line.startswith("DRAGON "):
            p = line.split()
            n = int(p[2])
            c = list(map(int, p[3:3 + 2 * n]))
            team[nid] = "AB"[int(p[1])]
            bodies[nid] = [(c[2 * i], c[2 * i + 1]) for i in range(n)]
            nid += 1
    rnd = 0
    for e in data["events"]:
        t = e["type"]
        if t == "roundStart":
            rnd = e["round"]
        elif t == "dragonUpdate" and e["id"] in bodies:
            b = bodies[e["id"]]
            b.insert(0, (e["head"]["x"], e["head"]["y"]))
            tail = (e["tail"]["x"], e["tail"]["y"])
            while len(b) > 1 and b[-1] != tail:
                b.pop()
        elif t == "dragonSplit":
            team[e["childId"]] = team[e["parentId"]]
            bodies[e["parentId"]] = [(p["x"], p["y"]) for p in e["parentBody"]]
            bodies[e["childId"]] = [(p["x"], p["y"]) for p in e["childBody"]]
        if callback:
            callback(rnd, e, team, bodies)
        if t == "dragonDeath":
            bodies.pop(e["id"], None)


def stats(data):
    timeline = []
    deaths = {t: collections.Counter() for t in "AB"}
    splits = {t: collections.Counter() for t in "AB"}
    sprints = {t: collections.Counter() for t in "AB"}
    sonar = collections.Counter()
    feed = collections.Counter()

    def cb(rnd, e, team, bodies):
        t = e["type"]
        if t == "roundStart" and rnd % 50 == 0:
            row = [rnd]
            for tm in "AB":
                ls = [len(b) for i, b in bodies.items() if team[i] == tm]
                row += [len(ls), max(ls or [0])]
            timeline.append(row)
        elif t == "dragonDeath":
            deaths[team[e["id"]]][e.get("reason")] += 1
        elif t == "dragonSplit":
            splits[team[e["parentId"]]][len(e["childBody"])] += 1
        elif t == "sonarPing":
            sonar[team[e["senderId"]]] += 1
        elif t == "dragonAction":
            tm = team[e["id"]]
            a = e["action"]
            if a["kind"] == "move":
                sprints[tm][len(a["steps"])] += 1
            elif a["kind"] == "suicide":
                h = bodies[e["id"]][0]
                near = any(j != e["id"] and team[j] == tm and len(b) >= 6
                           and abs(b[0][0] - h[0]) + abs(b[0][1] - h[1]) <= 4
                           for j, b in bodies.items())
                feed[(tm, "gan con dai" if near else "khac")] += 1

    simulate(data, cb)
    r = data["result"]
    name = next((l[9:] for l in data["map"].split("\n") if l.startswith("MAP_NAME")), "?")
    print(f"map {name}: thang = {r['winner'] or 'hoa'} ({r['endReason']})  A={r['teamA']}  B={r['teamB']}")
    print("  round | A: so con, dai nhat | B: so con, dai nhat")
    for row in timeline:
        print(f"  {row[0]:5d} | {row[1]:3d} {row[2]:3d} | {row[3]:3d} {row[4]:3d}")
    for tm in "AB":
        print(f"  team {tm}: chet={dict(deaths[tm])} split(kich thuoc con)={dict(splits[tm])} "
              f"sprint(so buoc)={dict(sprints[tm])} sonar={sonar[tm]} "
              f"tu sat={ {k[1]: v for k, v in feed.items() if k[0] == tm} }")


if __name__ == "__main__":
    args = sys.argv[1:]
    out_json = None
    if "--json" in args:
        i = args.index("--json")
        out_json = args[i + 1]
        del args[i:i + 2]
    for path in args:
        data = replay_to_json(path)
        if out_json:
            json.dump(data, open(out_json, "w"))
        print("=" * 70)
        print(path)
        stats(data)
