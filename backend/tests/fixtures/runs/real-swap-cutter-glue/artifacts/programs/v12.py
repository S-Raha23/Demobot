def clear(scene, robot, x, y, w, d, skip, avoid):
    for o in scene.objects():
        if o.name in skip or o.w > 20 or o.d > 20:
            continue
        if abs(o.x - x) < (o.w + w) / 2 + 2.5 and abs(o.y - y) < (o.d + d) / 2 + 2.5:
            robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=avoid))


def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    aw, ad, bw, bd = a.w, a.d, b.w, b.d
    skip = [a.name, b.name]
    avoid = [(ax, ay, aw + 8, ad + 8), (bx, by, aw + 8, ad + 8)]
    clear(scene, robot, ax, ay, aw, ad, skip, avoid)
    clear(scene, robot, bx, by, bw, bd, skip, avoid)
    tx, ty = scene.free_spot(size=(aw, ad), clearance=3)
    robot.move(scene.get(a.name), tx, ty)
    clear(scene, robot, ax, ay, bw, bd, skip, avoid)
    robot.move(scene.get(b.name), ax, ay)
    clear(scene, robot, bx, by, aw, ad, skip, avoid)
    robot.move(scene.get(a.name), bx, by)
