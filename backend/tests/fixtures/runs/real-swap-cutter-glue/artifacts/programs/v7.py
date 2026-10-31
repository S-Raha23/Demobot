def clear(scene, robot, cx, cy, w, d, skip, avoid):
    for o in scene.objects():
        if o.name in skip:
            continue
        if abs(o.x - cx) < (o.w + w) / 2 + 2 and abs(o.y - cy) < (o.d + d) / 2 + 2:
            robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=avoid + [(cx, cy, w + 6, d + 6)]))


def run(scene, robot):
    a = scene.get("teal box cutter")
    b = scene.get("glue bottle")
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    targets = [(ax, ay, b.w + 6, b.d + 6), (bx, by, a.w + 6, a.d + 6)]
    buf_x, buf_y = scene.free_spot(size=(b.w, b.d), clearance=2, avoid=targets)
    robot.move(scene.get(b.name), buf_x, buf_y)
    clear(scene, robot, bx, by, a.w, a.d, [a.name, b.name], targets + [(buf_x, buf_y, b.w + 6, b.d + 6)])
    robot.move(scene.get(a.name), bx, by)
    clear(scene, robot, ax, ay, b.w, b.d, [a.name, b.name], targets + [(bx, by, a.w + 6, a.d + 6)])
    robot.move(scene.get(b.name), ax, ay)
