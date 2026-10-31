def find_spot(scene, robot, obj, avoids, req):
    x0, y0, x1, y1 = scene.bounds()
    obs = [(o.x, o.y, o.w, o.d, o.h) for o in scene.objects() if o.name != obj.name]
    best = None
    bestd = 1e9
    gx = x0 + obj.w / 2 + 0.5
    while gx <= x1 - obj.w / 2 - 0.5:
        gy = y0 + obj.d / 2 + 0.5
        while gy <= y1 - obj.d / 2 - 0.5:
            if robot.can_reach(gx, gy):
                ok = True
                for ox, oy, ow, od, oh in obs:
                    need = req + (2.0 if oh > 5 or obj.h > 5 else 0.0)
                    if abs(gx - ox) < (obj.w + ow) / 2 + need and abs(gy - oy) < (obj.d + od) / 2 + need:
                        ok = False
                        break
                if ok:
                    for ax, ay, aw, ad in avoids:
                        if abs(gx - ax) < (obj.w + aw) / 2 + 1.5 and abs(gy - ay) < (obj.d + ad) / 2 + 1.5:
                            ok = False
                            break
                if ok:
                    dist = (gx - obj.x) ** 2 + (gy - obj.y) ** 2
                    if dist < bestd:
                        bestd = dist
                        best = (gx, gy)
            gy += 2.0
        gx += 2.0
    return best

def move_away(scene, robot, o, avoids):
    spot = find_spot(scene, robot, o, avoids, 2.0)
    if spot is None:
        spot = find_spot(scene, robot, o, avoids, 1.0)
    if spot is not None:
        robot.move(scene.get(o.name), spot[0], spot[1])

def clear_area(scene, robot, cx, cy, w, d, skip, avoids):
    for name in [o.name for o in scene.objects()]:
        if name in skip:
            continue
        o = scene.get(name)
        extra = 6.0 if o.h > 5 else 2.0
        if abs(o.x - cx) < (o.w + w) / 2 + extra and abs(o.y - cy) < (o.d + d) / 2 + extra:
            move_away(scene, robot, o, avoids)

def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    if not pens:
        return
    x0, y0, x1, y1 = scene.bounds()
    gap = 2.0
    spacing = 2.0
    totalw = sum(min(p.w, p.d) for p in pens)
    avail = (x1 - 0.5) - (box.x + box.w / 2)
    if len(pens) > 1 and gap + totalw + spacing * (len(pens) - 1) > avail:
        spacing = max(1.0, (avail - gap - totalw) / (len(pens) - 1))
    if gap + totalw + spacing * (len(pens) - 1) > avail:
        gap = 1.0
    infos = []
    cursor = box.x + box.w / 2 + gap
    for pen in pens:
        ew = min(pen.w, pen.d)
        ed = max(pen.w, pen.d)
        yaw = pen.yaw if pen.d >= pen.w else pen.yaw + 90
        tx = cursor + ew / 2
        ty = min(max(box.y, y0 + ed / 2 + 0.5), y1 - ed / 2 - 0.5)
        infos.append([pen.name, tx, ty, ew, ed, yaw])
        cursor += ew + spacing
    slots = [(i[1], i[2], i[3] + 8, i[4] + 8) for i in infos]
    placed = []
    pennames = [p.name for p in pens]
    for name, tx, ty, ew, ed, yaw in infos:
        skip = [box.name] + placed + pennames
        clear_area(scene, robot, tx, ty, ew, ed, skip, slots)
        pen = scene.get(name)
        clear_area(scene, robot, pen.x, pen.y, pen.w, pen.d, [box.name] + pennames, slots)
        clear_area(scene, robot, tx, ty, ew, ed, skip, slots)
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
