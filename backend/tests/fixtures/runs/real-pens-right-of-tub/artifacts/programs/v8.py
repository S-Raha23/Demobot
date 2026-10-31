def clear(scene, robot, cx, cy, w, d, skip, avoids, margin):
    for name in [o.name for o in scene.objects()]:
        if name in skip:
            continue
        o = scene.get(name)
        if abs(o.x - cx) < (o.w + w) / 2 + margin and abs(o.y - cy) < (o.d + d) / 2 + margin:
            robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3.0, avoid=avoids))

def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    x0, y0, x1, y1 = scene.bounds()
    infos = []
    cursor = box.x + box.w / 2 + 1.2
    for pen in pens:
        ew = min(pen.w, pen.d)
        ed = max(pen.w, pen.d)
        yaw = pen.yaw + 90 if pen.w > pen.d else pen.yaw
        tx = cursor + ew / 2
        ty = min(max(box.y, y0 + ed / 2 + 0.5), y1 - ed / 2 - 0.5)
        infos.append((pen.name, tx, ty, ew, ed, yaw))
        cursor += ew + 0.8
    slots = [(i[1], i[2], i[3] + 2, i[4] + 2) for i in infos]
    pnames = [i[0] for i in infos]
    placed = []
    for name, tx, ty, ew, ed, yaw in infos:
        skip = [box.name] + pnames + placed
        clear(scene, robot, tx, ty, ew, ed, skip, slots, 3.0)
        pen = scene.get(name)
        clear(scene, robot, pen.x, pen.y, pen.w, pen.d, skip, slots, 1.0)
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
