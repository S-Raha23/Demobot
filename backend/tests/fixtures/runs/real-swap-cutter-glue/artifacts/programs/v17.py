import math


def rgap(x, y, w, d, ox, oy, ow, od):
    dx = abs(x - ox) - (w + ow) / 2
    dy = abs(y - oy) - (d + od) / 2
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy)
    return max(dx, dy)


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    aw, ad, bw, bd = a.w, a.d, b.w, b.d
    skip = [a.name, b.name]
    avoid = [(ax, ay, aw + 4, ad + 4), (bx, by, aw + 4, ad + 4)]
    for cx, cy in [(ax, ay), (bx, by)]:
        for o in scene.objects():
            if o.name in skip or o.w * o.d > 150:
                continue
            limit = 5.0 if o.h > 5 else 1.0
            if rgap(cx, cy, aw, ad, o.x, o.y, o.w, o.d) < limit:
                robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=avoid))
    x0, y0, x1, y1 = scene.bounds()
    best = None
    bestscore = -9999.0
    objs = scene.objects()
    x = x0 + bw / 2
    while x <= x1 - bw / 2 + 0.01:
        y = y0 + bd / 2
        while y <= y1 - bd / 2 + 0.01:
            if robot.can_reach(x, y):
                ming = rgap(x, y, bw, bd, bx, by, aw, ad)
                for o in objs:
                    if o.name == b.name:
                        continue
                    g = rgap(x, y, bw, bd, o.x, o.y, o.w, o.d)
                    if g < ming:
                        ming = g
                score = min(ming, 8.0) - 0.01 * math.sqrt((x - ax) * (x - ax) + (y - ay) * (y - ay))
                if score > bestscore:
                    bestscore = score
                    best = (x, y)
            y += 1.0
        x += 1.0
    log("temp " + str(best) + " score " + str(round(bestscore, 2)))
    robot.move(scene.get(b.name), best[0], best[1])
    robot.move(scene.get(a.name), bx, by)
    robot.move(scene.get(b.name), ax, ay)
