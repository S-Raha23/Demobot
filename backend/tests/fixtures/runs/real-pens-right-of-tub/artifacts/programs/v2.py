def run(scene, robot):
    tub = scene.get("white tub")
    pens = scene.of_kind("pen")
    slots = []
    cursor = tub.x + tub.w / 2 + 2.0
    maxd = 0
    for pen in pens:
        eff_w = pen.d if pen.w > pen.d else pen.w
        eff_d = pen.w if pen.w > pen.d else pen.d
        maxd = max(maxd, eff_d)
        cx = cursor + eff_w / 2
        slots.append((pen.name, cx, eff_w, eff_d))
        cursor += eff_w + 1.5
    row_cx = (tub.x + tub.w / 2 + 2.0 + cursor) / 2
    row_w = cursor - (tub.x + tub.w / 2)
    row = (row_cx, tub.y, row_w + 4, maxd + 6)
    pen_names = [p.name for p in pens]
    for o in scene.objects():
        if o.name in pen_names or o.name == tub.name:
            continue
        hit = False
        for name, cx, ew, ed in slots:
            if abs(o.x - cx) < (o.w + ew) / 2 + 2 and abs(o.y - tub.y) < (o.d + ed) / 2 + 2:
                hit = True
        if hit:
            robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=2.0, avoid=[row]))
    for name, cx, ew, ed in slots:
        pen = scene.get(name)
        t = scene.get("white tub")
        yaw = pen.yaw + 90 if pen.w > pen.d else None
        log(f"moving {name} to {cx}, {t.y} yaw={yaw}")
        robot.move(pen, cx, t.y, yaw)
    robot.home()
