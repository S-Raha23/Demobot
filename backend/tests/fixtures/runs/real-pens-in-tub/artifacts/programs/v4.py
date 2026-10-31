def blockers_around(scene, cx, cy, skip):
    out = []
    for o in scene.objects():
        if o.name in skip or o.kind == "pen" or o.role == "container":
            continue
        if abs(o.x - cx) < o.w / 2 + 5 and abs(o.y - cy) < o.d / 2 + 5:
            out.append(o.name)
    return out


def run(scene, robot):
    tub = scene.get("white plastic tub")
    for pen in scene.of_kind("pen"):
        pen = scene.get(pen.name)
        tub = scene.get(tub.name)
        if scene.is_inside(pen, tub):
            continue
        skip = [pen.name, tub.name]
        names = blockers_around(scene, pen.x, pen.y, skip)
        for n in blockers_around(scene, tub.x, tub.y, skip):
            if n not in names:
                names.append(n)
        for n in names:
            b = scene.get(n)
            pen = scene.get(pen.name)
            tub = scene.get(tub.name)
            robot.move(b, *scene.free_spot(size=(b.w, b.d), clearance=3, avoid=[(pen.x, pen.y, 18, 18), (tub.x, tub.y, tub.w + 8, tub.d + 8)]))
        robot.pick(scene.get(pen.name))
        robot.place_in(scene.get(tub.name))
