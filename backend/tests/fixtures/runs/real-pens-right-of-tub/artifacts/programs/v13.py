def near(o, cx, cy, w, d, m):
    return abs(o.x - cx) < (o.w + w) / 2 + m and abs(o.y - cy) < (o.d + d) / 2 + m

def relocate(scene, robot, name, slots):
    o = scene.get(name)
    ew, ed, yaw = (o.d, o.w, o.yaw + 90) if o.w > o.d else (o.w, o.d, o.yaw)
    x0, y0, x1, y1 = scene.bounds()
    best, bests = None, -999.0
    for fx in [0.0, 0.25, 0.5, 0.75, 1.0]:
        x = x0 + ew / 2 + 0.5 + fx * (x1 - x0 - ew - 1)
        for fy in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = y0 + ed / 2 + 0.5 + fy * (y1 - y0 - ed - 1)
            if not robot.can_reach(x, y):
                continue
            s = 999.0
            for q in scene.objects():
                if q.name != name:
                    s = min(s, max(abs(x - q.x) - (ew + q.w) / 2, abs(y - q.y) - (ed + q.d) / 2))
            for sx, sy, sw, sd in slots:
                s = min(s, max(abs(x - sx) - (ew + sw) / 2, abs(y - sy) - (ed + sd) / 2))
            if s > bests:
                best, bests = (x, y), s
    robot.move(scene.get(name), best[0], best[1], yaw)

def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    x0, y0, x1, y1 = scene.bounds()
    infos = []
    cursor = box.x + box.w / 2 + 1.2
    for pen in pens:
        ew, ed = min(pen.w, pen.d), max(pen.w, pen.d)
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
        m = 7.0 if o.h > 5 else 3.0
        hit = any(near(o, i[1], i[2], i[3], i[4], m) for i in infos)
        hit = hit or any(near(o, p.x, p.y, p.w, p.d, m) for p in pens)
        hit = hit or (o.h > 5 and any(o.y > p.y and abs(o.x - p.x) < (o.w + p.w) / 2 + 7 for p in pens))
        if hit:
            movers.append(o)
    for o in sorted(movers, key=lambda q: -q.h):
        relocate(scene, robot, o.name, slots)
    for name, tx, ty, ew, ed, yaw in infos:
        robot.move(scene.get(name), tx, ty, yaw)
    robot.home()
