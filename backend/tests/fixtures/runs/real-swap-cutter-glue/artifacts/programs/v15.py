import math


def rgap(x, y, w, d, o):
    dx = abs(x - o.x) - (w + o.w) / 2
    dy = abs(y - o.y) - (d + o.d) / 2
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy)
    return max(dx, dy)


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    aw, ad, bw, bd = a.w, a.d, b.w, b.d
    skip = [a.name, b.name]
    avoid = [(ax, ay, aw + 6, ad + 6), (bx, by, aw + 6, ad + 6)]
    for cx, cy in [(bx, by), (ax, ay)]:
        for o in scene.objects():
            if o.name in skip or o.w * o.d > 150:
                continue
            limit = 4.0 if o.h > 5 else 0.5
            if rgap(cx, cy, aw, ad, o) < limit:
                robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=avoid))
    tx, ty = scene.free_spot(size=(bw, bd), clearance=2)
    robot.move(scene.get(b.name), tx, ty)
    robot.move(scene.get(a.name), bx, by)
    robot.move(scene.get(b.name), ax, ay)
