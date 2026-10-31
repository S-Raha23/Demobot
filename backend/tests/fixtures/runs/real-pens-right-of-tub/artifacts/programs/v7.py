def run(scene, robot):
    tub = scene.get("white tub")
    pens = scene.of_kind("pen")
    x0, y0, x1, y1 = scene.bounds()
    maxw = max(p.w for p in pens)
    horiz = tub.x + tub.w / 2 + 2.5 + maxw <= x1 - 0.5 and robot.can_reach(tub.x + tub.w / 2 + 2.5 + maxw / 2, tub.y)
    slots = []
    if horiz:
        cx = tub.x + tub.w / 2 + 2.5 + maxw / 2
        total = sum(p.d for p in pens) + 1.8 * (len(pens) - 1)
        cy = tub.y - total / 2
        for pen in pens:
            slots.append((pen.name, cx, cy + pen.d / 2, pen.w, pen.d))
            cy += pen.d + 1.8
        row = (cx, tub.y, maxw + 6, total + 6)
    else:
        cursor = tub.x + tub.w / 2 + 3.5
        maxd = max(max(p.w, p.d) for p in pens)
        for pen in pens:
            ew, ed = min(pen.w, pen.d), max(pen.w, pen.d)
            slots.append((pen.name, cursor + ew / 2, tub.y, ew, ed))
            cursor += ew + 1.8
        row = ((tub.x + tub.w / 2 + cursor) / 2, tub.y, cursor - tub.x + 8, maxd + 8)
    placed = []
    for name, cx, cy, ew, ed in slots:
        pen = scene.get(name)
        if not horiz and pen.w > pen.d:
            sx, sy = scene.free_spot(size=(pen.w, pen.w), clearance=2, avoid=[row])
            robot.move(pen, sx, sy, pen.yaw + 90)
        for o in scene.objects():
            if o.name == name or o.name == tub.name or o.name in placed:
                continue
            if abs(o.x - cx) < (o.w + ew) / 2 + 3 and abs(o.y - cy) < (o.d + ed) / 2 + 3:
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[row]))
        robot.move(scene.get(name), cx, cy)
        placed.append(name)
    robot.home()
