"""
arena.py - so sanh 2 bot tren nhieu map, nhieu seed, doi ben A/B cho cong bang.

Cach dung (chay trong thu muc chua maps/ va cac thu muc bot):
    python arena.py smartbot starter
    python arena.py smartbot_v2 smartbot --seeds 3 --jobs 4
    python arena.py smartbot starter --maps maps/arena.map maps/default.map
    python arena.py smartbot starter --fast          # khong dung sandbox (nhanh hon, khong do CPU)
    python arena.py smartbot starter --save-losses   # luu replay cac tran thua vao replays/losses/

Ket qua: ti le thang cua bot thu nhat + khoang tin cay 95%.
  - Neu can duoi (low) cua khoang tin cay > 50%  -> bot 1 manh hon THAT SU.
  - Neu khoang tin cay chua 50%                   -> chua du bang chung, chay them seed.
"""
import argparse
import concurrent.futures as cf
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import time

SEED_BASE = int(os.environ.get("SEED_BASE", "1000"))
ANSI = re.compile(r"\x1b\[[0-9;]*m")
RESULT = re.compile(r"(team ([AB]) wins|draw) after (\d+) rounds")
POINTS = re.compile(r"team ([AB]) points per turn: .* max ([\d.]+)M")


def run_game(unswbc, map_path, bot_a, bot_b, seed, sandbox, replay_dir):
    cmd = [unswbc, "run", map_path, bot_a, bot_b, "--seed", str(seed)]
    if sandbox:
        cmd.append("--sandbox")
    if replay_dir:
        cmd += ["-o", replay_dir, "--no-logs"]
    else:
        cmd.append("--no-replay")
    env = dict(os.environ, UNSWBC_NO_UPDATE="1", NO_COLOR="1")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env).stdout
    except subprocess.TimeoutExpired:
        return None, 0, {}, ["timeout"]
    out = ANSI.sub("", out)
    m = RESULT.search(out)
    winner = None
    rounds = 0
    if m:
        winner = m.group(2) if m.group(2) else "draw"
        rounds = int(m.group(3))
    pts = {t: float(v) for t, v in POINTS.findall(out)}
    problems = [l for l in out.splitlines() if "CPU limit" in l or "no valid action" in l
                or "error" in l.lower() or "traceback" in l.lower()]
    return winner, rounds, pts, problems


def wilson(wins, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot1")
    ap.add_argument("bot2")
    ap.add_argument("--maps", nargs="*", default=None)
    ap.add_argument("--seeds", type=int, default=2, help="so seed moi map (moi seed choi 2 tran doi ben)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--fast", action="store_true", help="khong dung --sandbox")
    ap.add_argument("--save-losses", action="store_true")
    args = ap.parse_args()

    unswbc = shutil.which("unswbc")
    if not unswbc:
        sys.exit("khong tim thay lenh unswbc - cai bang: pip install unswbc")
    maps = args.maps or sorted(glob.glob(os.path.join("maps", "*.map")))
    sandbox = not args.fast

    if sandbox:  # build/warm 1 lan truoc khi chay song song
        subprocess.run([unswbc, "run", maps[0], args.bot1, args.bot2, "--sandbox",
                        "--no-replay", "--seed", "1"], capture_output=True, text=True,
                       env=dict(os.environ, UNSWBC_NO_UPDATE="1"))

    jobs = []
    for mp in maps:
        for s in range(args.seeds):
            seed = SEED_BASE + s
            jobs.append((mp, seed, "A"))   # bot1 la team A
            jobs.append((mp, seed, "B"))   # bot1 la team B

    loss_dir = os.path.join("replays", "losses") if args.save_losses else None
    if loss_dir:
        os.makedirs(loss_dir, exist_ok=True)

    per_map = {}
    total = {"win": 0, "loss": 0, "draw": 0}
    max_pts = {args.bot1: 0.0, args.bot2: 0.0}
    all_problems = []
    t0 = time.time()

    def work(job):
        mp, seed, side = job
        a, b = (args.bot1, args.bot2) if side == "A" else (args.bot2, args.bot1)
        return job, run_game(unswbc, mp, a, b, seed, sandbox, None)

    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for job, (winner, rounds, pts, problems) in ex.map(work, jobs):
            mp, seed, side = job
            done += 1
            name = os.path.basename(mp).replace(".map", "")
            rec = per_map.setdefault(name, {"win": 0, "loss": 0, "draw": 0, "rounds": []})
            if winner is None or winner == "draw":
                res = "draw"
            else:
                res = "win" if winner == side else "loss"
            rec[res] += 1
            rec["rounds"].append(rounds)
            total[res] += 1
            other = "B" if side == "A" else "A"
            max_pts[args.bot1] = max(max_pts[args.bot1], pts.get(side, 0))
            max_pts[args.bot2] = max(max_pts[args.bot2], pts.get(other, 0))
            for p in problems:
                all_problems.append(f"{name} seed={seed} {args.bot1}=team{side}: {p}")
            print(f"[{done}/{len(jobs)}] {name:16s} seed={seed} {args.bot1}=team {side}: "
                  f"{res.upper():4s} ({rounds} rounds)", flush=True)
            if res == "loss" and loss_dir:
                a, b = (args.bot1, args.bot2) if side == "A" else (args.bot2, args.bot1)
                run_game(unswbc, mp, a, b, seed, sandbox, loss_dir)

    print()
    print(f"{'map':16s} {'W':>3s} {'L':>3s} {'D':>3s}  avg rounds")
    for name, r in per_map.items():
        avg = sum(r["rounds"]) / max(1, len(r["rounds"]))
        print(f"{name:16s} {r['win']:3d} {r['loss']:3d} {r['draw']:3d}  {avg:6.0f}")
    n = total["win"] + total["loss"] + total["draw"]
    score = total["win"] + 0.5 * total["draw"]
    lo, hi = wilson(score, n)
    print()
    print(f"{args.bot1} vs {args.bot2}: {total['win']}W {total['loss']}L {total['draw']}D "
          f"-> diem {100 * score / max(1, n):.1f}%  (95% CI {100 * lo:.0f}%-{100 * hi:.0f}%)")
    if lo > 0.5:
        print(f"=> {args.bot1} MANH HON {args.bot2} (co y nghia thong ke)")
    elif hi < 0.5:
        print(f"=> {args.bot1} YEU HON {args.bot2} (co y nghia thong ke)")
    else:
        print("=> Chua ket luan duoc: tang --seeds de co them du lieu")
    if sandbox:
        print(f"CPU max/luot (trieu diem, gioi han 100M): "
              + ", ".join(f"{k}={v:.1f}M" for k, v in max_pts.items()))
    if all_problems:
        print(f"\n{len(all_problems)} van de (CPU limit / loi):")
        for p in all_problems[:20]:
            print("  " + p)
    print(f"\nxong trong {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
