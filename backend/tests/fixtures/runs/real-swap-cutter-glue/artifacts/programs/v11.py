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
    x0, y0, x1, y1 = scene.bounds()
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    objs = scene.objects()
    best = None
    bestscore = -9999.0
    x = x0 + a.w / 2
    while x <= x1 - a.w / 2 + 0.01:
        y = y0 + a.d / 2
        while y <= y1 - a.d / 2 + 0.01:
            if robot.can_reach(x, y):
                ming = 999.0
                for o in objs:
                    if o.name == a.name:
                        continue
                    g = rgap(x, y, a.w, a.d, o.x, o.y, o.w, o.d)
                    if o.h > 5:
                        g = g - 1.5
                    if g < ming:
                        ming = g
                g = rgap(x, y, a.w, a.d, ax, ay, b.w, b.d) - 1.5
                if g < ming:
                    ming = g
                dc = math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy))
                score = min(ming, 8.0) - 0.01 * dc
                if score > bestscore:
                    bestscore = score
                    best = (x, y)
            y += 1.0
        x += 1.0
    log("parking cutter at " + str(best) + " score " + str(round(bestscore, 2)))
    robot.move(scene.get(a.name), best[0], best[1])
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
