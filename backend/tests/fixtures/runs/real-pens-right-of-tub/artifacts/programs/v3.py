def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    if not pens:
        return
    x0, y0, x1, y1 = scene.bounds()
    infos = []
    cursor = box.x + box.w / 2 + 2.0
    for pen in pens:
        ew = min(pen.w, pen.d)
        ed = max(pen.w, pen.d)
        yaw = pen.yaw if pen.d >= pen.w else pen.yaw + 90
        tx = cursor + ew / 2
        ty = min(max(box.y, y0 + ed / 2 + 0.5), y1 - ed / 2 - 0.5)
        infos.append([pen.name, tx, ty, ew, ed, yaw])
        cursor += ew + 1.5
    overflow = (cursor - 1.5) - (x1 - 0.5)
    if overflow > 0:
        for info in infos:
            info[1] -= overflow
    slots = [(i[1], i[2], i[3] + 4, i[4] + 4) for i in infos]
    placed = []
    for name, tx, ty, ew, ed, yaw in infos:
        fresh_box = scene.get("white box")
        if not robot.can_reach(tx, ty):
            tx, ty = scene.free_spot(near=fresh_box, side="right_of", size=(ew, ed), clearance=2)
        for o in scene.objects():
            if o.name == name or o.name == fresh_box.name or o.name in placed:
                continue
            if abs(o.x - tx) < (o.w + ew) / 2 + 2 and abs(o.y - ty) < (o.d + ed) / 2 + 2:
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=slots))
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
