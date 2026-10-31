import math


def rgap(x, y, w, d, o):
    dx = abs(x - o.x) - (w + o.w) / 2
    dy = abs(y - o.y) - (d + o.d) / 2
    if dx > 0 and dy > 0:
        return math.sqrt(dx * dx + dy * dy)
    return max(dx, dy)


def clear_dest(scene, robot, x, y, w, d, skip, avoid):
    for o in scene.objects():
        if o.name in skip or (o.w > 15 and o.d > 10):
            continue
        limit = 5.0 if o.h > 5 else 3.0
        if rgap(x, y, w, d, o) < limit:
            robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=avoid))


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    aw, ad, bw, bd = a.w, a.d, b.w, b.d
    skip = [a.name, b.name]
    tx, ty = scene.free_spot(size=(aw, ad), clearance=2)
    avoid = [(ax, ay, bw + 6, bd + 6), (bx, by, aw + 6, ad + 6), (tx, ty, aw + 6, ad + 6)]
    robot.move(scene.get(a.name), tx, ty)
    clear_dest(scene, robot, ax, ay, bw, bd, skip, avoid)
    robot.move(scene.get(b.name), ax, ay)
    clear_dest(scene, robot, bx, by, aw, ad, skip, avoid)
    robot.move(scene.get(a.name), bx, by)
