def clear(scene, robot, x, y, w, d, skip, avoid):
    for o in scene.objects():
        if o.name in skip:
            continue
        if abs(o.x - x) < (o.w + w) / 2 + 2 and abs(o.y - y) < (o.d + d) / 2 + 2:
            robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=avoid))

def run(scene, robot):
    a = scene.get("white cylinder")
    b = scene.get("gray block")
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    avoid = [(ax, ay, b.w + 4, b.d + 4), (bx, by, a.w + 4, a.d + 4)]
    tx, ty = scene.free_spot(size=(a.w, a.d), clearance=3)
    robot.move(scene.get(a.name), tx, ty)
    b_fresh = scene.get(b.name)
    clear(scene, robot, ax, ay, b_fresh.w, b_fresh.d, [a.name, b.name], avoid)
    robot.move(scene.get(b.name), ax, ay)
    a_fresh = scene.get(a.name)
    clear(scene, robot, bx, by, a_fresh.w, a_fresh.d, [a.name, b.name], avoid)
    robot.move(scene.get(a.name), bx, by)
