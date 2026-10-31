import math


def gap(x, y, w, d, o):
    dx = abs(x - o.x) - (w + o.w) / 2
    dy = abs(y - o.y) - (d + o.d) / 2
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy)
    return max(dx, dy)


def spot(scene, robot, item, ax, ay, bx, by):
    x0, y0, x1, y1 = scene.bounds()
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    best = None
    bestscore = -9999.0
    x = x0 + item.w / 2
    while x <= x1 - item.w / 2:
        y = y0 + item.d / 2
        while y <= y1 - item.d / 2:
            if robot.can_reach(x, y):
                ming = 999.0
                for o in scene.objects():
                    if o.name == item.name:
                        continue
                    g = gap(x, y, item.w, item.d, o)
                    if g < ming:
                        ming = g
                da = math.sqrt((x - ax) * (x - ax) + (y - ay) * (y - ay)) - 3
                db = math.sqrt((x - bx) * (x - bx) + (y - by) * (y - by)) - 3
                ming = min(ming, da, db)
                dc = math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy))
                score = min(ming, 9.0) - 0.03 * dc
                if score > bestscore:
                    bestscore = score
                    best = (x, y)
            y += 1.0
        x += 1.0
    return best


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    temp = spot(scene, robot, a, ax, ay, bx, by)
    log("parking cutter at " + str(temp))
    robot.move(scene.get(a.name), temp[0], temp[1])
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
