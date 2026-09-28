"""Bighero V9 = V8 + late-game feeding of the longest dragon (keeper).

V8: selective head attacks, covered splits, and portal scouting.

Per-dragon memory uses only observations received through protocol 3.
Unknown portal exits are scouting risks, not assumed empty.
"""

import helper as unswbc
from helper import Direction, EdgeType


DIRECTIONS = Direction.get_direction_list()
OFFSETS = [direction.get_offset() for direction in DIRECTIONS]
ct: unswbc.Controller
game: unswbc.Game
last_visit = {}
known_neck = None
previous_action = None


def observe_neck(here):
    """Remember only the body cell a completed single move proves occupied.

    A successful single step, including portal transit, leaves the old head
    as the new neck. Splitting preserves the parent's first two segments.
    A sprint has a different neck, so discard this fact after multiple steps.
    Fresh children start with independent, empty history.
    """
    global known_neck
    if previous_action is None:
        known_neck = None
    else:
        action, origin = previous_action
        if action == "move" and here != origin:
            known_neck = origin
        elif action != "split" or here != origin:
            known_neck = None


def neighbours(position, width, height):
    """Four neighbouring coordinates, including wraparound at map borders."""
    x, y = position
    return [((x + dx) % width, (y + dy) % height) for dx, dy in OFFSETS]


def visible_graph(tiles, occupied, width, height):
    """Normal, currently empty routes inside the 7x7 vision window.

    Portals are deliberately excluded: their destination is not the adjacent
    tile. The emergency fallback below can use one when normal moves fail.
    Frontier edges lead outside vision; they are possibilities, not safe tiles.
    """
    graph = {}
    frontier = {}
    for position, tile in tiles.items():
        exits = []
        unknown_exits = 0
        for direction, destination in zip(
            DIRECTIONS, neighbours(position, width, height)
        ):
            if tile.get_edge(direction).get_edge_type() != EdgeType.EMPTY:
                continue
            if destination not in tiles:
                unknown_exits += 1
            elif destination not in occupied:
                exits.append(destination)
        graph[position] = exits
        frontier[position] = unknown_exits
    return graph, frontier


def head_risks(tiles, graph, dragon_id, own_team):
    """Estimate which visible free tiles other heads can reach next turn.

    The opponent's full length can lie outside vision, so two sprint steps are
    considered possible for every visible enemy head. Three steps require at
    least four of that dragon's segments to be visible. Portals are unknown.
    """
    danger = {}
    visible_parts = {}
    for tile in tiles.values():
        part = tile.get_dragon()
        if part is not None:
            visible_parts[part.get_id()] = visible_parts.get(part.get_id(), 0) + 1
    for position, tile in tiles.items():
        part = tile.get_dragon()
        if part is None or not part.is_head() or part.get_id() == dragon_id:
            continue
        enemy = part.get_team() != own_team
        steps = 3 if enemy and visible_parts[part.get_id()] >= 4 else (2 if enemy else 1)
        frontier = {position}
        visited = {position}
        for depth in range(1, steps + 1):
            following = set()
            for source in frontier:
                for destination in graph[source]:
                    if destination not in visited:
                        following.add(destination)
            penalty = (1350, 1050, 480)[depth - 1] if enemy else 440
            if enemy and ct.get_unit_count() >= 4 and ct.get_length() <= 3:
                penalty *= 0.12 if ct.get_length() == 2 else 0.35
            for destination in following:
                danger[destination] = max(danger.get(destination, 0), penalty)
            visited.update(following)
            frontier = following
    return danger


def can_spread(tiles, graph, here, width, height, round_num, danger):
    """Split only when both resulting heads have room for the next move."""
    if round_num >= FEED_ROUND and ct.get_unit_count() >= FEED_MIN_UNITS * 2:
        return False
    if round_num >= 400 or ct.get_unit_count() >= min(game.get_unit_limit(), 60):
        return False
    # Preserve a longer dragon for the 500-round length tiebreak. Split it
    # early for coverage, then let it collect pearls after the team has grown.
    leaders = (0, 2) if ct.get_team().value == "A" else (1, 3)
    # A long child created by a reverse split inherits the scoring role.
    # Length identifies the role even for children born during round zero.
    if ct.get_length() >= 6:
        return False
    if ct.get_id() in leaders and (round_num >= 75 or ct.get_unit_count() >= 12):
        return False
    # Renew scoring roles after original leaders die. A small deterministic
    # subset keeps growing once a healthy population can fund that role.
    if (round_num >= 130 and ct.get_unit_count() >= 10
            and ct.get_id() % 7 == 0):
        return False
    if round_num >= 250 and ct.get_unit_count() >= 12 and ct.get_length() >= 6:
        return False
    if not ct.can_split(2) or not graph[here]:
        return False

    tail = visible_tail(tiles, width, height)
    if tail is None or not graph[tail]:
        return False

    return min(danger.get(position, 0) for position in graph[here]) < 1050


def visible_tail(tiles, width, height):
    """Validate the complete body chain, including links through known portals."""
    own_parts = {
        position: tile.get_dragon()
        for position, tile in tiles.items()
        if tile.get_dragon() is not None
        and tile.get_dragon().get_id() == ct.get_id()
    }
    if len(own_parts) != ct.get_length():
        return None
    heads = [position for position, part in own_parts.items() if part.is_head()]
    if len(heads) != 1:
        return None
    behind = {}
    for position, part in own_parts.items():
        # A head's facing is its last move, not another body link.
        if part.is_head():
            continue
        direction = part.get_dir()
        edge = tiles[position].get_edge(direction)
        if edge.get_edge_type() == EdgeType.PORTAL:
            ahead = portal_destination(position, direction, edge.get_portal_id(), width, height)
        elif edge.get_edge_type() == EdgeType.EMPTY:
            ahead = neighbours(position, width, height)[DIRECTIONS.index(direction)]
        else:
            return None
        if ahead not in own_parts or ahead in behind:
            return None
        behind[ahead] = position
    current = heads[0]
    seen = {current}
    while current in behind:
        current = behind[current]
        if current in seen:
            return None
        seen.add(current)
    return current if len(seen) == len(own_parts) else None


def inspect_route(start, graph, frontier, tiles, danger, round_num):
    """Flood fill visible free space and find nearby, less risky pearls."""
    queue = [start]
    distances = {start: 0}
    cursor = 0
    nearest_pearl = None
    future_pearl = None
    frontier_count = 0
    new_space = 0
    while cursor < len(queue):
        position = queue[cursor]
        cursor += 1
        distance = distances[position]
        frontier_count += frontier[position]
        age = round_num - last_visit.get(position, -1000)
        if age > 20:
            new_space += 1
        if tiles[position].has_pearl() and danger.get(position, 0) < 1000 and position not in RESERVED:
            if nearest_pearl is None or distance < nearest_pearl:
                nearest_pearl = distance
        countdown = tiles[position].get_pearl_time()
        if (not tiles[position].has_pearl() and 1 <= countdown <= distance <= 4
                and danger.get(position, 0) < 1000):
            if future_pearl is None or distance < future_pearl:
                future_pearl = distance
        for destination in graph[position]:
            if destination not in distances:
                distances[destination] = distance + 1
                queue.append(destination)
    return len(distances), nearest_pearl, frontier_count, new_space, future_pearl


ATTACK_LENGTH = 3
ATTACK_RATIO = 0.8

def tactical_attack(tiles, graph, here):
    """Trade a small expendable dragon for a reachable enemy head.

    Movement is sequential, so this is an exact same-turn collision, not a
    prediction of where the enemy might move. Never sacrifice the last unit.
    """
    if ct.get_unit_count() < 3 or ct.get_length() > ATTACK_LENGTH:
        return None
    width, height = game.get_map_size()
    queue = [(here, [])]
    seen = {here}
    best = None
    best_value = -1
    parts = {}
    for tile in tiles.values():
        part = tile.get_dragon()
        if part is not None:
            parts[part.get_id()] = parts.get(part.get_id(),0) + 1
    for p, route in queue:
        if len(route) >= min(ct.get_length()-1, 4):
            continue
        for direction, q in zip(DIRECTIONS, neighbours(p, width, height)):
            if tiles[p].get_edge(direction).get_edge_type() != EdgeType.EMPTY or q not in tiles:
                continue
            part = tiles[q].get_dragon()
            if part is not None:
                if part.is_head() and part.get_team() != ct.get_team():
                    value = parts[part.get_id()] - ct.get_length() * ATTACK_RATIO - len(route)*0.1
                    if value > best_value and value >= 0:
                        best, best_value = route + [direction], value
                continue
            if q not in seen:
                seen.add(q)
                queue.append((q,route + [direction]))
    return best


"""Inserted into candidates: portal topology learned from each dragon's vision."""
portal_edges = {}
portal_used = {}
recent_heads = []

def edge_key(p, direction, width, height):
    x, y = p
    index = DIRECTIONS.index(direction)
    if index % 2 == 0:
        return (0, x, (y + (index == 2)) % height)
    return (1, (x + (index == 1)) % width, y)

def remember_portals(tiles, here, width, height):
    recent_heads.append(here)
    if len(recent_heads) > 24:
        del recent_heads[0]
    for p, tile in tiles.items():
        for direction in DIRECTIONS:
            edge = tile.get_edge(direction)
            if edge.get_edge_type() == EdgeType.PORTAL:
                portal_edges.setdefault(edge.get_portal_id(), set()).add(edge_key(p, direction, width, height))

def portal_destination(p, direction, portal_id, width, height):
    source = edge_key(p, direction, width, height)
    ends = portal_edges.get(portal_id, set()) - {source}
    if len(ends) != 1:
        return None
    axis, x, y = next(iter(ends))
    if direction == Direction.NORTH:
        y = (y - 1) % height
    elif direction == Direction.WEST:
        x = (x - 1) % width
    return x, y

def portal_action(portal_options, tiles, occupied, here, graph, frontier, danger,
                  width, height, round_num, best_score):
    if not portal_options:
        return None
    best = None
    area, pearl, borders, new_space, future = inspect_route(here, graph, frontier, tiles, danger, round_num)
    stagnant = len(recent_heads) >= 16 and len(set(recent_heads)) <= 10
    for direction in portal_options:
        portal_id = tiles[here].get_edge(direction).get_portal_id()
        q = portal_destination(here, direction, portal_id, width, height)
        if q in occupied:
            continue
        fresh = round_num - portal_used.get(portal_id, -1000) > 32
        if q in tiles:
            a, p, b, n, f = inspect_route(q, graph, frontier, tiles, danger, round_num)
            exits = graph[q]
            score = 5*min(a,35) + 20*min(len(exits),3)
            score += 18*min(sum(danger.get(x,0)<1050 for x in exits),2)
            score += 3*min(b,6)+min(n,12)-danger.get(q,0)
            if tiles[q].has_pearl():
                score += 140 if ct.get_length() <= 4 else 135
            score += 100/(p+1) if p is not None else 150/(f+1) if f is not None else 0
            score -= max(0,18-(round_num-last_visit.get(q,-1000)))*4
            if not exits and not frontier[q]:
                score -= 5000
            if b == 0 and a < min(ct.get_length()+2,16):
                score -= 90*(min(ct.get_length()+2,16)-a)
            score += resource_bonus.get(direction, 0)
        elif (q is not None and fresh and ct.get_length() <= 4 and ct.get_unit_count() >= 3
              and resource_bonus.get(direction, 0) >= 40):
            # The remote exit is unseen: permit only a redundant scout when
            # remembered terrain actually connects it to a plausible meal.
            score = best_score + 8
        elif (fresh and ct.get_length() <= 4 and ct.get_unit_count() >= 3
              and ((pearl is None and future is None and area < 24) or stagnant)):
            # An unseen destination is explicitly a scouting risk. Only send
            # short redundant dragons out of unproductive/looping components.
            score = max(120, best_score + 15)
        else:
            score = -2000 if fresh else -2600
        if score > best_score:
            best_score, best = score, direction
    if best is not None:
        portal_id = tiles[here].get_edge(best).get_portal_id()
        portal_used[portal_id] = round_num
    return best


# Per-dragon observations only. Static terrain may be remembered; old food and
# occupancy are never assumed certain when choosing an immediate action.
resource_memory = {}
resource_goal = None
resource_bonus = {}


def remember_resources(tiles, width, height, round_num):
    for p, tile in tiles.items():
        exits = []
        for direction, q in zip(DIRECTIONS, neighbours(p, width, height)):
            edge = tile.get_edge(direction)
            kind = edge.get_edge_type()
            if kind == EdgeType.EMPTY:
                exits.append((direction, q))
            elif kind == EdgeType.PORTAL:
                q = portal_destination(p, direction, edge.get_portal_id(), width, height)
                if q is not None:
                    exits.append((direction, q))
        countdown = tile.get_pearl_time()
        due = round_num + countdown if countdown >= 0 else None
        resource_memory[p] = (round_num, tile.has_pearl(), due, tuple(exits))
    # Bound both persistent storage and the work needed to rank old records.
    if len(resource_memory) > 384:
        oldest = sorted(resource_memory, key=lambda p: resource_memory[p][0])
        for p in oldest[:len(resource_memory) - 384]:
            del resource_memory[p]


def remembered_food_value(record, round_num, distance):
    seen, pearl, due, _ = record
    age = max(0, round_num - seen)
    if pearl:
        return max(0, 1 - age / 30)
    # Distance one is a move now, before the next round-start spawn attempt.
    # A predicted spawn is uncertain: another body may have blocked it.
    if due is None or due > round_num + distance - 1:
        return 0
    return 0.5 * max(0, 1 - age / 50)


def plan_resources(here, tiles, occupied, danger, round_num):
    """Give an otherwise fruitless explorer one remembered, reachable goal.

    Search at most 192 previously observed cells and 16 steps. Current bodies
    block routes. The ordinary movement policy still checks immediate safety;
    old terrain supplies navigation, not a promise of an empty destination.
    """
    global resource_goal
    resource_bonus.clear()
    queue = [here]
    routes = {here: (0, None)}
    for p in queue:
        distance, first = routes[p]
        if distance >= 16 or len(routes) >= 192:
            continue
        record = resource_memory.get(p)
        if record is None:
            continue
        for direction, q in record[3]:
            if q in occupied or q in routes or q not in resource_memory:
                continue
            routes[q] = distance + 1, first if first is not None else direction
            queue.append(q)
            if len(routes) >= 192:
                break
    # Fresh local pearls already get a strong, verified score in the main
    # policy. Keep old memories from distracting a dragon that can eat now.
    if any(p in tiles and distance <= 4 and tiles[p].has_pearl()
           and danger.get(p, 0) < 1000
           for p, (distance, _) in routes.items() if distance):
        return
    best, best_score, best_first = None, 0, None
    for p, (distance, first) in routes.items():
        if not distance or (p in tiles and danger.get(p, 0) >= 1000):
            continue
        probability = remembered_food_value(resource_memory[p], round_num, distance)
        if probability <= 0:
            continue
        score = probability / (distance + 2)
        if p == resource_goal:
            score *= 1.2
        if score > best_score:
            best, best_score, best_first = p, score, first
    resource_goal = best
    if best is not None:
        cap = 90
        resource_bonus[best_first] = min(cap, 30 + 500 * best_score)


# ---------------------------------------------------------------------------
# V9: FEEDING. Tiebreak at round 500 = longest living dragon. Top teams convert
# their swarm into length: small dragons walk next to their longest ally and
# suicide, dropping pearls (every 2nd segment) that the keeper eats.
# Keepers broadcast their position with sonar so feeders can find them.
# ---------------------------------------------------------------------------
FEED_ROUND = 330          # feeding phase starts
FEED_SATURATED_ROUND = 150  # ... or earlier when the team is at the unit limit
FEED_MAX_LEN = 4          # only dragons this short feed
FEED_MIN_UNITS = 8        # keep at least this many dragons alive (before END_ROUND)
MERGE_ROUND = 400         # from here, mid-length dragons also feed a longer keeper
END_ROUND = 470           # from here everybody but the keeper may feed
RESERVE_RADIUS = 3        # pearls this close to a keeper head are left for it
RESERVED = set()
KEEPER_MIN_LEN = 6        # visible ally parts to count as a keeper
KEEPER_GUARD_LEN = 9      # dragons this long play extra safe
MAGIC = 0xB16E
keeper_info = None        # (x, y, round, length) heard via sonar


def feeding_phase(round_num):
    units = ct.get_unit_count()
    if round_num >= FEED_ROUND:
        return True
    return round_num >= FEED_SATURATED_ROUND and units >= game.get_unit_limit() - 1


def encode_keeper(x, y, round_num, length):
    return (MAGIC << 48) | ((round_num & 511) << 39) | ((x & 63) << 33) | ((y & 63) << 27) | ((length & 255) << 19)


def read_sonar(round_num):
    global keeper_info
    for value in ct.get_sonar_messages():
        if value >> 48 != MAGIC:
            continue
        r = (value >> 39) & 511
        x = (value >> 33) & 63
        y = (value >> 27) & 63
        length = (value >> 19) & 255
        if r > round_num or round_num - r > 20:
            continue
        if (keeper_info is None or round_num - keeper_info[2] > 8
                or length > keeper_info[3] or (length == keeper_info[3] and r > keeper_info[2])):
            keeper_info = (x, y, r, length)


def broadcast(round_num, here):
    """Keepers announce themselves; recent news is relayed by small dragons."""
    if round_num < FEED_ROUND - 40:
        return
    length = ct.get_length()
    msg = None
    if length >= KEEPER_MIN_LEN:
        if keeper_info is None or length >= keeper_info[3] or round_num - keeper_info[2] > 6:
            msg = encode_keeper(here[0], here[1], round_num, length)
    elif keeper_info is not None and round_num - keeper_info[2] <= 3:
        msg = encode_keeper(keeper_info[0], keeper_info[1], keeper_info[2], keeper_info[3])
    if msg is not None:
        for direction in DIRECTIONS:
            ct.send_sonar(direction, msg)


def visible_keeper(tiles):
    """Longest visible ally (other than me) whose head is in view."""
    counts = {}
    heads = {}
    me = ct.get_id()
    team = ct.get_team()
    for p, tile in tiles.items():
        part = tile.get_dragon()
        if part is None or part.get_team() != team or part.get_id() == me:
            continue
        counts[part.get_id()] = counts.get(part.get_id(), 0) + 1
        if part.is_head():
            heads[part.get_id()] = p
    best = None
    need = max(KEEPER_MIN_LEN, ct.get_length() + 3)
    for i, c in counts.items():
        if i in heads and c >= need and (best is None or c > best[1]):
            best = (heads[i], c)
    return best


def bfs_dist(start, graph, limit):
    dist = {start: 0}
    queue = [start]
    for p in queue:
        d = dist[p]
        if d >= limit:
            continue
        for q in graph.get(p, ()):
            if q not in dist:
                dist[q] = d + 1
                queue.append(q)
    return dist


feed_bonus = {}


def plan_feeding(tiles, graph, here, width, height, round_num, danger):
    """Returns 'suicide' when this dragon should die here to feed a keeper.
    Otherwise fills feed_bonus with a pull towards the keeper."""
    feed_bonus.clear()
    RESERVED.clear()
    if not feeding_phase(round_num):
        return None
    length = ct.get_length()
    keeper = visible_keeper(tiles)
    if keeper is not None:
        # leave the pearls around a longer ally for it
        kx, ky = keeper[0]
        for p, tile in tiles.items():
            if tile.has_pearl():
                dx = min((p[0] - kx) % width, (kx - p[0]) % width)
                dy = min((p[1] - ky) % height, (ky - p[1]) % height)
                if dx + dy <= RESERVE_RADIUS:
                    RESERVED.add(p)
    units = ct.get_unit_count()
    min_units = 3 if round_num >= END_ROUND else FEED_MIN_UNITS
    if units < min_units:
        return None
    if length > FEED_MAX_LEN and round_num < MERGE_ROUND:
        return None
    if keeper is not None:
        khead, klen = keeper
        # distance for the keeper through currently free tiles; my own body will
        # vanish when I die, so let the keeper path reach my head tile.
        own = {p for p, t in tiles.items() if t.get_dragon() is not None and t.get_dragon().get_id() == ct.get_id()}
        kgraph = {}
        for p, tile in tiles.items():
            exits = []
            for direction, q in zip(DIRECTIONS, neighbours(p, width, height)):
                if q in tiles and tile.get_edge(direction).get_edge_type() == EdgeType.EMPTY:
                    tq = tiles[q].get_dragon()
                    if tq is None or q in own:
                        exits.append(q)
            kgraph[p] = exits
        kd = bfs_dist(khead, kgraph, 5)
        busy = any(tiles[p].has_pearl() for p, d in kd.items() if 0 < d <= 3)
        mine = kd.get(here)
        if mine is not None and mine <= 2 and not busy:
            return "suicide"
        # walk towards the keeper
        md = bfs_dist(khead, graph, 12)
        for direction, q in zip(DIRECTIONS, neighbours(here, width, height)):
            if q in md and md[q] >= 1:
                cur = md.get(here, 99)
                if md[q] < cur:
                    feed_bonus[direction] = 70
        return None
    if (keeper_info is not None and round_num - keeper_info[2] <= 15
            and keeper_info[3] >= length + 3):
        kx, ky = keeper_info[0], keeper_info[1]
        dx = (kx - here[0]) % width
        dy = (ky - here[1]) % height
        if dx:
            feed_bonus[Direction.EAST if dx <= width // 2 else Direction.WEST] = 45
        if dy:
            feed_bonus[Direction.SOUTH if dy <= height // 2 else Direction.NORTH] = 45
    return None


def choose_action():
    width, height = game.get_map_size()
    round_num = game.get_round_num()
    head = ct.get_position()
    here = (head.x, head.y)
    last_visit[here] = round_num
    observe_neck(here)

    tiles = {}
    occupied = set()
    for tile in ct.get_tiles():
        position = tile.get_position()
        key = (position.x, position.y)
        tiles[key] = tile
        if tile.get_dragon() is not None:
            occupied.add(key)

    # The neck may be on the unseen side of a portal. It is still occupied
    # now: collisions are resolved before the tail can vacate.
    if known_neck is not None:
        occupied.add(known_neck)

    remember_portals(tiles, here, width, height)
    remember_resources(tiles, width, height, round_num)
    graph, frontier = visible_graph(tiles, occupied, width, height)
    danger = head_risks(tiles, graph, ct.get_id(), ct.get_team())
    read_sonar(round_num)
    broadcast(round_num, here)
    attack = tactical_attack(tiles, graph, here)
    if attack:
        return attack, "attack"
    if plan_feeding(tiles, graph, here, width, height, round_num, danger) == "suicide":
        return None, "feed"
    if can_spread(tiles, graph, here, width, height, round_num, danger):
        return None, "split"
    plan_resources(here, tiles, occupied, danger, round_num)
    current_tile = tiles[here]
    best_direction = None
    best_score = float("-inf")
    portal_options = []

    big_keeper = ct.get_length() >= KEEPER_GUARD_LEN and round_num >= 200
    enemy_heads = [p for p, t in tiles.items()
                   if t.get_dragon() is not None and t.get_dragon().is_head()
                   and t.get_dragon().get_team() != ct.get_team()]
    # Rotate tie-breaking by dragon ID so allies need not choose alike.
    rotation = ct.get_id() % 4
    order = DIRECTIONS[rotation:] + DIRECTIONS[:rotation]
    for direction in order:
        edge = current_tile.get_edge(direction).get_edge_type()
        if edge == EdgeType.KELP:
            continue
        if edge == EdgeType.PORTAL:
            q = portal_destination(here, direction, current_tile.get_edge(direction).get_portal_id(), width, height)
            if q not in occupied:
                portal_options.append(direction)
            continue

        destination_obj = head.add_dir(direction)
        destination = (destination_obj.x, destination_obj.y)
        # The game checks collision BEFORE the tail moves, so the tail stays
        # blocked here even when this move would otherwise remove it.
        if destination not in tiles or destination in occupied:
            continue

        area, pearl_distance, borders, new_space, future_pearl = inspect_route(
            destination, graph, frontier, tiles, danger, round_num
        )
        exits = graph[destination]
        safe_exits = sum(danger.get(p, 0) < 1050 for p in exits)
        score = (4 if ct.get_length() <= 4 else 5) * min(area, 35) + (6 if ct.get_length() <= 4 else 20) * min(len(exits), 3)
        score += (6 if ct.get_length() <= 4 else 18) * min(safe_exits, 2)
        score += 3 * min(borders, 6) + min(new_space, 12)

        if not exits and not frontier[destination]:
            score -= 5000
        # Small closed areas are unattractive; bodies may move later, so this
        # is a penalty, not a claim that the route is certainly fatal.
        if borders == 0 and area < min(ct.get_length() + 2, 16):
            score -= 90 * (min(ct.get_length() + 2, 16) - area)

        score -= danger.get(destination, 0)
        if big_keeper:
            # V9: a long dragon is the tiebreak: never gamble it near enemy heads
            score -= 2 * danger.get(destination, 0)
            for eh in enemy_heads:
                dd = (min((eh[0] - destination[0]) % width, (destination[0] - eh[0]) % width)
                      + min((eh[1] - destination[1]) % height, (destination[1] - eh[1]) % height))
                if dd <= 4:
                    score -= (5 - dd) * 90
        if tiles[destination].has_pearl() and destination not in RESERVED:
            score += 140 if ct.get_length() <= 4 else 135
        if pearl_distance is not None:
            score += (260 if ct.get_length() <= 4 else 220) / (pearl_distance + 1)
        elif future_pearl is not None:
            score += (180) / (future_pearl + 1)

        # A recent visit is a gentle penalty, not a ban on following our tail.
        age = round_num - last_visit.get(destination, -1000)
        score -= max(0, 18 - age) * 2
        score += resource_bonus.get(direction, 0)
        score += feed_bonus.get(direction, 0)
        if direction == ct.get_dir():
            score += 2

        if score > best_score:
            best_score = score
            best_direction = direction

    portal = portal_action(portal_options, tiles, occupied, here, graph, frontier, danger,
                           width, height, round_num, best_score)
    if portal is not None:
        return portal, "portal planned"
    if best_direction is not None:
        destination_obj = head.add_dir(best_direction)
        destination = (destination_obj.x, destination_obj.y)
        tail = visible_tail(tiles, width, height)
        tail_opens = (tail is not None and not tiles[destination].has_pearl()
                      and any(q == tail and tiles[destination].get_edge(d).get_edge_type()
                              == EdgeType.EMPTY
                              for d, q in zip(DIRECTIONS,
                                              neighbours(destination, width, height))))
        # A route with no visible exit, no frontier and no portal has no
        # planned follow-up. Give the tail child a chance to survive instead
        # of walking the head into that one-step cul-de-sac.
        if (ct.can_split(2) and not tail_opens and not graph[destination]
                and not frontier[destination]
                and not any(tiles[destination].get_edge(d).get_edge_type()
                            == EdgeType.PORTAL for d in DIRECTIONS)):
            return None, "rescue split"
        return best_direction, "move"
    if portal_options:
        # The far end is unknown: take a chance only when normal moves fail.
        return portal_options[ct.get_id() % len(portal_options)], "portal escape"
    if ct.can_split(2):
        return None, "rescue split"
    # With no survival move, do not also kill a friendly head when a wall,
    # body collision, or enemy-head collision can spare it.
    for direction, adjacent in zip(DIRECTIONS, neighbours(here, width, height)):
        edge = current_tile.get_edge(direction)
        if edge.get_edge_type() == EdgeType.KELP:
            return direction, "no open route"
        destination = (portal_destination(here, direction, edge.get_portal_id(), width, height)
                       if edge.get_edge_type() == EdgeType.PORTAL else adjacent)
        part = tiles[destination].get_dragon() if destination in tiles else None
        if part is not None and (not part.is_head() or part.get_id() == ct.get_id()
                                 or part.get_team() != ct.get_team()):
            return direction, "no open route"
    # A valid action is mandatory even when every immediate route is blocked.
    return ct.get_dir(), "no open route"


def execute_turn():
    global previous_action
    direction, reason = choose_action()
    head = ct.get_position()
    origin = (head.x, head.y)
    if reason == "feed":
        previous_action = ("feed", origin)
        ct.set_indicator_string("V9: feed")
        return
    if reason in ("split", "rescue split"):
        size = ct.get_length() - 2 if reason == "rescue split" and ct.get_length() >= 6 else 2
        previous_action = ("split", origin)
        ct.do_split(size)
        ct.set_indicator_string("V8: split " + str(size))
    elif reason == "attack":
        previous_action = ("move" if len(direction) == 1 else "sprint", origin)
        ct.make_moves(direction)
        ct.set_indicator_string("V8: attack " + "".join(d.value for d in direction))
    else:
        previous_action = ("move", origin)
        ct.make_move(direction)
        ct.set_indicator_string("V8: " + reason + " " + direction.value)


def main():
    global ct, game
    ct, game = unswbc.init()
    while unswbc.update(ct, game):
        execute_turn()
        unswbc.end_turn()


if __name__ == "__main__":
    main()
