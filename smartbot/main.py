"""
smartbot - UNSW Battlecode bot (Python)

Moi dragon chay 1 process rieng (con sinh ra tu split la process moi, khong co tri nho).
Moi luot:
  1. QUAN SAT : nho kelp/portal (khong bao gio doi), ngoc, dong ho sinh ngoc, o da thay.
  2. SNIPE    : team con >= 2 dragon va thay dau dich trong tam sprint -> lao vao dau dich
               (ca hai cung chet). Neu dich chi con 1 dragon -> minh thang ngay.
  3. SPLIT    : du dai thi tach con -> "bao hiem", kho bi tieu diet het.
  4. DI CHUYEN: cham diem 4 huong = muc tieu (ngoc / ngoc sap sinh / vung chua kham pha)
               + an toan (flood fill: con du cho, khong tu nhot minh)
               - nguy hiem (gan dau dich, co the bi dam dau).

Luu y CPU: judge tinh ~450 diem / bytecode Python, gioi han 100M diem / luot.
Vi vay code dung list phang + cache ke (ADJ) thay vi goi ham trong vong lap.
"""
import time
_now = time.perf_counter_ns          # trong sandbox: 1 ns ~ 1 diem CPU
TURN_START = _now()
import helper as unswbc
from helper import Direction, EdgeType

# ------------------------------------------------------------------
# NUT CHINH - sua roi chay arena.py de so sanh voi ban cu
# ------------------------------------------------------------------
SPLIT_AT = 10            # dai >= SPLIT_AT thi tach con
SPLIT_CHILD = 4          # do dai con tach ra (>= 2)
MAX_UNITS = 3            # so dragon toi da minh muon co
SPLIT_LAST_ROUND = 380   # sau round nay khong tach nua (giu con dai nhat cho tiebreak)
SNIPE = True             # bat/tat chien thuat dam dau
SNIPE_MIN_UNITS = 2      # chi dam dau khi team con >= bao nhieu dragon
SNIPE_MAX_STEPS = 6      # sprint toi da bao nhieu buoc de dam
BFS_LIMIT = 450          # so o toi da BFS tim muc tieu (gioi han CPU)
EXPLORE_W = 0.3          # trong so kham pha
BUDGET = 45_000_000      # dung BFS khi luot da ton chung nay diem (gioi han judge: 100M)
HARD_LIMIT = 62_000_000  # phanh khan cap cho moi vong lap khac
DEBUG = False            # True -> hien diem tung huong tren replay

DIRS = Direction.get_direction_list()      # N E S W
DIR_IDX = {d: k for k, d in enumerate(DIRS)}
UNK, EMPTY, KELP = -2, -1, -3
INF = 1 << 30
T_EMPTY, T_KELP = EdgeType.EMPTY, EdgeType.KELP

ct: unswbc.Controller
game: unswbc.Game
W = H = N = 0
NBR = []          # NBR[i] = (bac, dong, nam, tay) - chi so o ke (chua tinh portal/kelp)
ADJ = []          # ADJ[i] = list (o_dich, huong) di duoc; None = can tinh lai
edge_h = []       # canh phia BAC cua o i
edge_v = []       # canh phia TAY cua o i
portals = {}      # portal id -> list (kind, idx)
PEARL = []        # PEARL[i] = round cuoi thay ngoc o i, -1 neu khong
SPAWN = []        # SPAWN[i] = round du doan o i sinh ngoc, -1 neu chua biet
LS = []           # LS[i] = round cuoi nhin thay o i
VIS = []          # dau thoi gian cho BFS
stamp = 0
trail = []        # lich su vi tri dau -> suy ra than minh
my_team = None
my_dir = 0


def nbrs(i):
    r = NBR[i]
    if r is None:
        x = i % W
        y = i // W
        r = NBR[i] = (x + ((y - 1) % H) * W, (x + 1) % W + y * W,
                      x + ((y + 1) % H) * W, (x - 1) % W + y * W)
    return r


def mdist(a, b):
    dx = abs(a % W - b % W)
    dy = abs(a // W - b // W)
    if dx + dx > W:
        dx = W - dx
    if dy + dy > H:
        dy = H - dy
    return dx + dy


def edge_tiles(kind, idx):
    return (idx, nbrs(idx)[0]) if kind == 0 else (idx, nbrs(idx)[3])


def set_edge(arr, kind, idx, e):
    t = e.edge_type
    if t is T_EMPTY:
        arr[idx] = EMPTY
    elif t is T_KELP:
        arr[idx] = KELP
    else:
        pid = e.portal_id
        arr[idx] = pid
        lst = portals.setdefault(pid, [])
        key = (kind, idx)
        if key not in lst:
            lst.append(key)
            if len(lst) >= 2:          # biet ca 2 dau portal -> tinh lai ke
                for k2, i2 in lst:
                    for tt in edge_tiles(k2, i2):
                        ADJ[tt] = None
    a, b = edge_tiles(kind, idx)
    ADJ[a] = None
    ADJ[b] = None


def step(i, d):
    """O dich khi di 1 buoc huong d tu o i. -1 = kelp, -2 = portal chua biet dau ra."""
    n = nbrs(i)
    if d == 0:
        e = edge_h[i]
    elif d == 1:
        e = edge_v[n[1]]
    elif d == 2:
        e = edge_h[n[2]]
    else:
        e = edge_v[i]
    if e == KELP:
        return -1
    if e < 0:
        return n[d]
    key = (0, i) if d == 0 else (1, n[1]) if d == 1 else (0, n[2]) if d == 2 else (1, i)
    for kind, p in portals.get(e, ()):
        if (kind, p) != key:
            if kind == 0:
                return p if d == 2 else nbrs(p)[0]
            return p if d == 1 else nbrs(p)[3]
    return -2


def adj(i):
    a = ADJ[i]
    if a is None:
        a = []
        for d in range(4):
            v = step(i, d)
            if v >= 0:
                a.append((v, d))
        ADJ[i] = a
    return a


def observe(rnd):
    parts = []
    eh, ev = edge_h, edge_v
    for t in ct.get_tiles():
        p = t.position
        i = p.x + p.y * W
        LS[i] = rnd
        PEARL[i] = rnd if t.pearl else -1
        pt = t.pearl_time
        if pt >= 0:
            SPAWN[i] = rnd + pt
        n = NBR[i] or nbrs(i)
        if eh[i] == UNK:
            set_edge(eh, 0, i, t._edges[0])
        if ev[n[1]] == UNK:
            set_edge(ev, 1, n[1], t._edges[1])
        if eh[n[2]] == UNK:
            set_edge(eh, 0, n[2], t._edges[2])
        if ev[i] == UNK:
            set_edge(ev, 1, i, t._edges[3])
        if t.dragon_part is not None:
            parts.append((i, t.dragon_part))
    return parts


def snipe_path(head, goals, OCC, max_steps):
    """Duong ngan nhat (list huong) toi dau dich, toi da max_steps buoc."""
    global stamp
    stamp += 1
    VIS[head] = stamp
    prev = {head: None}
    frontier = [head]
    t = 0
    while frontier and t < max_steps:
        nxt = []
        for u in frontier:
            for v, d in (ADJ[u] or adj(u)):
                if VIS[v] == stamp:
                    continue
                if v in goals:
                    path = [d]
                    while u != head:
                        pu, pd = prev[u]
                        path.append(pd)
                        u = pu
                    path.reverse()
                    return path
                VIS[v] = stamp
                if OCC[v] > t + 1:
                    continue
                prev[v] = (u, d)
                nxt.append(v)
        frontier = nxt
        t += 1
    return None


def space(start, OCC, cap):
    """So o toi duoc tu start (than minh rut dan theo thoi gian)."""
    global stamp
    stamp += 1
    VIS[start] = stamp
    frontier = [start]
    cnt = 1
    t = 1
    while frontier:
        t += 1
        nxt = []
        for u in frontier:
            for v, d in (ADJ[u] or adj(u)):
                if VIS[v] != stamp and OCC[v] <= t:
                    VIS[v] = stamp
                    nxt.append(v)
        cnt += len(nxt)
        if cnt >= cap or _now() > TURN_START + HARD_LIMIT:
            return cnt
        frontier = nxt
    return cnt


def escape_split(L, OCC, cap, best_space):
    """Dang bi ket. Neu duoi dang o cho thoang -> tach con lon (L-2) chui ra tu duoi.
    Neu khong -> cat 2 dot duoi (dung yen 1 luot) de duoi tien dan ra cho thoang."""
    global trail
    if len(trail) >= L:
        tail = trail[-L]
        child_best = 0
        for v, _ in (ADJ[tail] or adj(tail)):
            if OCC[v] == 0:
                cs = space(v, OCC, cap)
                if cs > child_best:
                    child_best = cs
        if child_best >= 6 and child_best > best_space and ct.can_split(L - 2):
            if DEBUG:
                ct.set_indicator_string(f"ESCAPE {child_best}")
            ct.do_split(L - 2)
            trail = trail[-2:]
            return True
    if best_space <= 2 and ct.can_split(2):
        if DEBUG:
            ct.set_indicator_string("SHED")
        ct.do_split(2)
        trail = trail[-(L - 2):]
        return True
    return False


def execute_turn() -> None:
    global my_dir, trail, stamp
    rnd = game.round_num
    L = ct.length
    units = ct.unit_count
    my_id = ct.head.dragon_id
    hp = ct.head.position
    head = hp.x + hp.y * W
    my_dir = DIRS.index(ct.head.dir)

    if not trail or trail[-1] != head:
        trail.append(head)
    if len(trail) > L + 8:
        trail = trail[-(L + 8):]

    parts = observe(rnd)
    t_obs = _now()

    # process moi (con tu split) chua co lich su -> dung lai than tu tam nhin
    if len(trail) < L:
        own = {}
        for i, part in parts:
            if part.dragon_id == my_id and i != head:
                own[i] = DIR_IDX[part.dir]
        chain = [head]
        cur = head
        while own:
            found = -1
            for i, dd in own.items():
                if nbrs(i)[dd] == cur:
                    found = i
                    break
            if found < 0:
                break
            del own[found]
            chain.append(found)
            cur = found
        if len(chain) > len(trail):
            trail = chain[::-1]

    # ---- OCC[i] = buoc thu may thi o i moi trong (0 = trong ngay) ----
    OCC = [0] * N
    body = trail[-L:]
    k = 2
    for p in body:
        OCC[p] = k
        k += 1
    bodyset = set(body)
    eheads = []           # (idx, do dai nhin thay)
    enemy_len = {}
    ehead_ids = []
    ally_heads = []
    for i, part in parts:
        did = part.dragon_id
        if did == my_id:
            if i not in bodyset:
                OCC[i] = INF
            continue
        OCC[i] = INF
        if part.team is my_team:
            if part.is_dragon_head:
                ally_heads.append(i)
        else:
            enemy_len[did] = enemy_len.get(did, 0) + 1
            if part.is_dragon_head:
                ehead_ids.append((i, did))
    for i, did in ehead_ids:
        eheads.append((i, enemy_len[did]))

    # ---- 1. SNIPE: dam dau dich ----
    if SNIPE and eheads and units >= SNIPE_MIN_UNITS:
        goals = set()
        for i, el in eheads:
            if el + 3 >= L or L <= 6:
                goals.add(i)
        if goals:
            path = snipe_path(head, goals, OCC, min(L - 1, SNIPE_MAX_STEPS) if L > 2 else 1)
            if path:
                if DEBUG:
                    ct.set_indicator_string("SNIPE")
                if len(path) == 1:
                    ct.make_move(DIRS[path[0]])
                else:
                    ct.make_moves([DIRS[d] for d in path])
                return

    near_enemy = 99
    for i, _ in eheads:
        md = mdist(head, i)
        if md < near_enemy:
            near_enemy = md

    # ---- 2. SPLIT (dung yen 1 luot, an toan) ----
    if (L >= SPLIT_AT and units < MAX_UNITS and rnd <= SPLIT_LAST_ROUND
            and near_enemy > 3 and ct.can_split(SPLIT_CHILD)):
        ct.do_split(SPLIT_CHILD)
        trail = trail[-(L - SPLIT_CHILD):]
        return

    # ---- 3. Cac nuoc di hop le ----
    legal = {}
    fallback = None
    for d in range(4):
        v = step(head, d)
        if v == -2:
            fallback = d
            continue
        if v < 0 or OCC[v] > 1:
            continue
        legal[d] = v
    if not legal:
        if L >= 4 and escape_split(L, OCC, 16, 0):
            return
        ct.make_move(DIRS[fallback if fallback is not None else my_dir])
        return

    # ---- 4. An toan truoc (quan trong nhat): flood fill tung huong ----
    cap = L + 6
    if cap < 16:
        cap = 16
    elif cap > 48:
        cap = 48
    need = L + 4 if L + 4 < cap else cap
    spaces = {}
    for d, v in legal.items():
        spaces[d] = space(v, OCC, cap)
    t_sp = _now()

    # ---- 4b. Bi ket (moi huong deu thieu cho) -> split de phan duoi thoat ----
    best_space = max(spaces.values())
    if L >= 4 and best_space < min(L + 1, need):
        if escape_split(L, OCC, cap, best_space):
            return

    # ---- 5. BFS tu dau: mask = cac huong buoc dau cho duong ngan nhat ----
    stamp += 1
    st = stamp
    DIST = {}
    MASK = {}
    q = []
    for d, v in legal.items():
        if VIS[v] == st:
            MASK[v] |= 1 << d
        else:
            VIS[v] = st
            DIST[v] = 1
            MASK[v] = 1 << d
            q.append(v)
    VIS[head] = st
    best = [-1e9, -1e9, -1e9, -1e9]
    end_game = rnd >= 480
    ew = 0.0 if end_game else EXPLORE_W
    qi = 0
    limit = BFS_LIMIT
    deadline = TURN_START + BUDGET
    while qi < len(q) and qi < limit:
        if qi & 7 == 0 and _now() > deadline:
            break
        u = q[qi]
        qi += 1
        t = DIST[u]
        m = MASK[u]
        # --- gia tri o u ---
        pv = PEARL[u]
        if pv >= 0:
            val = 100.0 - 3.0 * (rnd - pv)
            if val < 30.0:
                val = 30.0
        else:
            sa = SPAWN[u]
            val = 0.0
            if sa >= 0:
                wait = sa - rnd - t + 1
                if wait <= 0:
                    if LS[u] < sa:
                        val = 55.0
                elif wait < 7:
                    val = 55.0 - 8.0 * wait
        if val > 0.0 and eheads:
            for ei, _ in eheads:
                de = mdist(ei, u)
                if de < t:
                    val *= 0.3
                elif de == t:
                    val *= 0.6
        age = rnd - LS[u]
        ev = (40 if age > 40 else age) * ew
        if ev > val:
            val = ev
        score = val - 3.0 * t
        if m == 1 or m == 2 or m == 4 or m == 8:
            d = 0 if m == 1 else 1 if m == 2 else 2 if m == 4 else 3
            if score > best[d]:
                best[d] = score
        else:
            for d in range(4):
                if m >> d & 1 and score > best[d]:
                    best[d] = score
        # --- mo rong ---
        nt = t + 1
        for v, _ in (ADJ[u] or adj(u)):
            if VIS[v] != st:
                if OCC[v] > nt:
                    continue
                VIS[v] = st
                DIST[v] = nt
                MASK[v] = m
                q.append(v)
            elif DIST.get(v) == nt:
                MASK[v] |= m

    t_bfs = _now()
    # ---- 6. Cham diem ----
    scores = {}
    for d, v in legal.items():
        s = best[d] if best[d] > -1e8 else 0.0
        sp = spaces[d]
        if sp < need:
            s -= 1500 - 30 * sp
        danger = 0.0
        for ei, el in eheads:
            md = mdist(v, ei)
            if md <= 1:
                danger += 600
            elif md == 2:
                danger += 120
            elif md == 3:
                danger += 30
        for ai in ally_heads:
            if mdist(v, ai) <= 1:
                danger += 80
        if units >= 2 and L <= 5:
            danger *= 0.4
        if end_game:
            danger *= 2
        s -= danger
        if d == my_dir:
            s += 2
        scores[d] = s

    d = max(scores, key=scores.get)
    if DEBUG and _now() - TURN_START > 55_000_000:
        ct.output_log("SLOW", (t_obs - TURN_START) // 10**6, (t_sp - TURN_START) // 10**6,
                      (t_bfs - TURN_START) // 10**6, (_now() - TURN_START) // 10**6, qi, L)
    if DEBUG:
        ct.set_indicator_string(" ".join(f"{DIRS[k].value}{int(x)}" for k, x in scores.items()))
    ct.make_move(DIRS[d])
    trail.append(legal[d])


def main() -> None:
    global TURN_START
    global ct, game, W, H, N, NBR, ADJ, edge_h, edge_v, PEARL, SPAWN, LS, VIS, my_team
    ct, game = unswbc.init()
    W, H = game.width, game.height
    N = W * H
    NBR = [None] * N
    ADJ = [None] * N
    edge_h = [UNK] * N
    edge_v = [UNK] * N
    PEARL = [-1] * N
    SPAWN = [-1] * N
    LS = [-1000] * N
    VIS = [0] * N
    my_team = ct.get_team()

    while unswbc.update(ct, game):
        try:
            execute_turn()
        except Exception as e:  # khong de bot crash: crash = chet
            ct.make_move(DIRS[my_dir])
            if DEBUG:
                ct.output_log("ERR", repr(e))
        unswbc.end_turn()
        TURN_START = _now()


if __name__ == "__main__":
    main()
