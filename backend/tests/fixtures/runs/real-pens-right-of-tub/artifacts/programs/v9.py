import math

def hd(o):
    return math.hypot(o.w, o.d) / 2

def spot(scene, robot, o, pts, rad):
    x0, y0, x1, y1 = scene.bounds()
    best = ((x0 + x1) / 2, (y0 + y1) / 2)
    bs = -9999
    for gx in range(int(x0 + rad + 1), int(x1 - rad), 4):
        for gy in range(int(y0 + rad + 1), int(y1 - rad), 4):
            if not robot.can_reach(gx, gy):
                continue
            s = min([math.hypot(gx - q.x, gy - q.y) - rad - hd(q) for q in scene.objects() if q.name != o.name] + [math.hypot(gx - px, gy - py) - rad - 8 for px, py in pts] + [99])
            if s > bs:
                bs = s
                best = (gx, gy)
    return best

def clear(scene, robot, cx, cy, w, d, skip, pts):
    for o in scene.objects():
        if o.name in skip:
            continue
        ex = 7 if o.h > 5 else 3
        if abs(o.x - cx) < (o.w + w) / 2 + ex and abs(o.y - cy) < (o.d + d) / 2 + ex:
            b = scene.get(o.name)
            robot.move(b, *spot(scene, robot, b, pts, hd(b)))

def run(scene, robot):
    tub = scene.get("white tub")
    pens = scene.of_kind("pen")
    x0, y0, x1, y1 = scene.bounds()
    slots = []
    cursor = tub.x + tub.w / 2 + 3.5
    maxd = max(max(p.w, p.d) for p in pens)
    for pen in pens:
        ew, ed = min(pen.w, pen.d), max(pen.w, pen.d)
        slots.append((pen.name, cursor + ew / 2, tub.y, ew, ed))
        cursor += ew + 1.8
    if slots[-1][1] + slots[-1][3] / 2 > x1 - 0.5 or tub.y - maxd / 2 < y0 or tub.y + maxd / 2 > y1:
        maxw = max(p.w for p in pens)
        cx = tub.x + tub.w / 2 + 2.5 + maxw / 2
        total = sum(p.d for p in pens) + 1.8 * (len(pens) - 1)
        cy = tub.y - total / 2
        slots = []
        for pen in pens:
            slots.append((pen.name, cx, cy + pen.d / 2, pen.w, pen.d))
            cy += pen.d + 1.8
    pts = [(cx, cy) for name, cx, cy, ew, ed in slots]
    names = [p.name for p in pens]
    placed = []
    for name, cx, cy, ew, ed in slots:
        pen = scene.get(name)
        clear(scene, robot, pen.x, pen.y, pen.w, pen.d, names + [tub.name] + placed, pts)
        pen = scene.get(name)
        if pen.w > ew + 0.1:
            robot.move(pen, *spot(scene, robot, pen, pts, max(pen.w, pen.d) / 2), pen.yaw + 90)
        clear(scene, robot, cx, cy, ew, ed, [name, tub.name] + placed, pts)
        robot.move(scene.get(name), cx, cy)
        placed.append(name)
    robot.home()
