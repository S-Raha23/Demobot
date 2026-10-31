def run(scene, robot):
    tub = scene.get("white tub")
    pens = scene.of_kind("pen")
    slots = []
    cursor = tub.x + tub.w / 2 + 3.5
    maxd = 0
    for pen in pens:
        ew = min(pen.w, pen.d)
        ed = max(pen.w, pen.d)
        maxd = max(maxd, ed)
        slots.append((pen.name, cursor + ew / 2, ew, ed))
        cursor += ew + 1.8
    row_cx = (tub.x + tub.w / 2 + cursor) / 2
    row = (row_cx, tub.y, cursor - tub.x + 8, maxd + 8)
    names = [p.name for p in pens]
    for name, cx, ew, ed in slots:
        tub = scene.get("white tub")
        for o in scene.objects():
            if o.name in names or o.name == tub.name:
                continue
            if abs(o.x - cx) < (o.w + ew) / 2 + 3 and abs(o.y - tub.y) < (o.d + ed) / 2 + 3:
                pen_now = scene.get(name)
                avoid = [row, (pen_now.x, pen_now.y, pen_now.w + 8, pen_now.d + 8)]
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=avoid))
        pen = scene.get(name)
        if pen.w > pen.d:
            sx, sy = scene.free_spot(size=(pen.w, pen.w), clearance=2, avoid=[row])
            robot.move(pen, sx, sy, pen.yaw + 90)
            pen = scene.get(name)
        tub = scene.get("white tub")
        robot.move(pen, cx, tub.y)
    robot.home()
