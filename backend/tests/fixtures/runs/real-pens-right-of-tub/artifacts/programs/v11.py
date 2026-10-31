def near(o, cx, cy, w, d, m):
    return abs(o.x - cx) < (o.w + w) / 2 + m and abs(o.y - cy) < (o.d + d) / 2 + m

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
    movers = []
    for o in scene.objects():
        if o.name == box.name or o.name in pnames:
            continue
        hit = any(near(o, i[1], i[2], i[3], i[4], 3.0) for i in infos)
        hit = hit or any(near(o, p.x, p.y, p.w, p.d, 4.0) for p in pens)
        if hit:
            movers.append(o.name)
    for nm in movers:
        o = scene.get(nm)
        robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=1.0, avoid=slots))
    placed = []
    for name, tx, ty, ew, ed, yaw in infos:
        for nm in [o.name for o in scene.objects()]:
            if nm == box.name or nm in pnames or nm in placed:
                continue
            o = scene.get(nm)
            pen = scene.get(name)
            if near(o, tx, ty, ew, ed, 3.0) or near(o, pen.x, pen.y, pen.w, pen.d, 4.0):
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=1.0, avoid=slots))
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
