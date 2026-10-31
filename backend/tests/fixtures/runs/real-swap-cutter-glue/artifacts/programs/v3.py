def find_temp(scene, item, other, ax, ay, bx, by):
    x0, y0, x1, y1 = scene.bounds()
    midx = (x0 + x1) / 2
    px, py = (ax, ay) if item.name == scene.get("light blue box cutter").name else (bx, by)
    qx, qy = (bx, by) if px == ax else (ax, ay)
    if item.x == bx and item.y == by:
        px, py, qx, qy = bx, by, ax, ay
    best = None
    best_score = -1000000.0
    objs = scene.objects()
    for xi in range(int(x0 + item.w / 2 + 1), int(x1 - item.w / 2), 1):
        for yi in range(int(y0 + item.d / 2 + 1), int(y1 - item.d / 2), 1):
            x = float(xi)
            y = float(yi)
            if not robot_can(scene, x, y):
                continue
            ok = True
            for o in objs:
                if o.name == item.name:
                    continue
                extra = 6.0 if o.h > 5 else 0.0
                if abs(x - o.x) < (item.w + o.w) / 2 + 1.5 + extra and abs(y - o.y) < (item.d + o.d) / 2 + 1.5 + extra:
                    ok = False
            if abs(x - px) < (item.w + other.w) / 2 + 1.5 and abs(y - py) < (item.d + other.d) / 2 + 1.5:
                ok = False
            if abs(x - qx) < item.w + 1.5 and abs(y - qy) < item.d + 1.5:
                ok = False
            if not ok:
                continue
            score = y - 0.2 * abs(x - midx)
            if score > best_score:
                best_score = score
                best = (x, y)
    return best


def robot_can(scene, x, y):
    return x >= scene.bounds()[0] and x <= scene.bounds()[2]


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    # park glue (small) first: find temp by scanning with can_reach check via robot
    x0, y0, x1, y1 = scene.bounds()
    midx = (x0 + x1) / 2
    best = None
    best_score = -1000000.0
    for xi in range(int(x0 + b.w / 2 + 1), int(x1 - b.w / 2), 1):
        for yi in range(int(y0 + b.d / 2 + 1), int(y1 - b.d / 2), 1):
            x = float(xi)
            y = float(yi)
            if not robot.can_reach(x, y):
                continue
            ok = True
            for o in scene.objects():
                if o.name == b.name:
                    continue
                extra = 6.0 if o.h > 5 else 0.0
                if abs(x - o.x) < (b.w + o.w) / 2 + 1.5 + extra and abs(y - o.y) < (b.d + o.d) / 2 + 1.5 + extra:
                    ok = False
            if abs(x - bx) < (b.w + b.w) / 2 + 1.5 and abs(y - by) < (b.d + b.d) / 2 + 1.5:
                ok = False
            if abs(x - ax) < (b.w + b.w) / 2 + 1.5 and abs(y - ay) < (b.d + b.d) / 2 + 1.5:
                ok = False
            if abs(x - bx) < (b.w + a.w) / 2 + 1.5 and abs(y - by) < (b.d + a.d) / 2 + 1.5:
                ok = False
            if not ok:
                continue
            score = y - 0.2 * abs(x - midx)
            if score > best_score:
                best_score = score
                best = (x, y)
    log("temp for glue: " + str(best))
    robot.move(scene.get(b.name), best[0], best[1])
    robot.move(scene.get(a.name), bx, by)
    robot.move(scene.get(b.name), ax, ay)
