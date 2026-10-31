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
    def clear(placed):
        for nm in [o.name for o in scene.objects()]:
            if nm == box.name or nm in pnames or nm in placed:
                continue
            o = scene.get(nm)
            slot_hit = any(near(o, i[1], i[2], i[3], i[4], 3.0) for i in infos if i[0] not in placed)
            start_hit = o.h <= 5 and any(near(o, scene.get(p).x, scene.get(p).y, scene.get(p).w, scene.get(p).d, 3.0) for p in pnames if p not in placed)
            if slot_hit or start_hit:
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=1.0, avoid=slots))
    clear([])
    placed = []
    for name, tx, ty, ew, ed, yaw in infos:
        clear(placed)
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
