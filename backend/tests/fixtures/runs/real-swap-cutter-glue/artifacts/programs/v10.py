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
    best = None
    bestscore = -9999.0
    x = x0 + b.w / 2
    while x <= x1 - b.w / 2:
        y = y0 + b.d / 2
        while y <= y1 - b.d / 2:
            if robot.can_reach(x, y):
                ming = 999.0
                for o in scene.objects():
                    if o.name == b.name:
                        continue
                    g = rgap(x, y, b.w, b.d, o.x, o.y, o.w, o.d)
                    if o.h > 5:
                        g = g - 1.5
                    if g < ming:
                        ming = g
                hg = rgap(x, y, b.w, b.d, bx, by, a.w, a.d)
                if hg < ming:
                    ming = hg
                da = math.sqrt((x - ax) * (x - ax) + (y - ay) * (y - ay))
                db = math.sqrt((x - bx) * (x - bx) + (y - by) * (y - by))
                score = min(min(da, db), 4 * ming) - 0.02 * abs(x - (x0 + x1) / 2)
                if score > bestscore:
                    bestscore = score
                    best = (x, y)
            y += 0.5
        x += 0.5
    log("parking glue at " + str(best) + " score " + str(bestscore))
    robot.move(scene.get(b.name), best[0], best[1])
    robot.move(scene.get(a.name), bx, by)
    robot.move(scene.get(b.name), ax, ay)
