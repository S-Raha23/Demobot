def eff(o):
    n = abs(o.yaw) % 180
    if n > 45 and n < 135:
        return (o.d, o.w)
    return (o.w, o.d)


def overlaps(o, cx, cy, w, d):
    ew, ed = eff(o)
    return abs(o.x - cx) < (ew + w) / 2 and abs(o.y - cy) < (ed + d) / 2


def clear(scene, robot, cx, cy, w, d, skip):
    for o in scene.objects():
        if o.name in skip:
            continue
        ew, ed = eff(o)
        if ew > 11 and ed > 11:
            continue
        if overlaps(o, cx, cy, w, d):
            robot.move(scene.get(o.name), *scene.free_spot(size=(ew, ed), clearance=1.5, avoid=[(cx, cy, w + 4, d + 4)]))


def run(scene, robot):
    a = scene.get("teal box cutter")
    b = scene.get("glue bottle")
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    aw, ad = eff(a)
    bw, bd = eff(b)
    buf_x, buf_y = scene.free_spot(size=(bw + 1, bd + 1), clearance=3)
    robot.move(scene.get(b.name), buf_x, buf_y)
    ayaw = None
    for o in scene.objects():
        ew, ed = eff(o)
        if ew > 11 and ed > 11 and overlaps(o, bx, by, aw, ad) and not overlaps(o, bx, by, ad, aw):
            aw, ad = ad, aw
            ayaw = a.yaw + 90
            break
    clear(scene, robot, bx, by, aw, ad, [a.name, b.name])
    robot.move(scene.get(a.name), bx, by, yaw=ayaw)
    clear(scene, robot, ax, ay, bw, bd, [a.name, b.name])
    robot.move(scene.get(b.name), ax, ay)
