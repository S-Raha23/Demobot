def scan(scene, obj, avoids, req):
    x0, y0, x1, y1 = scene.bounds()
    best = None
    bestd = 1e9
    gx = math.ceil(x0 + obj.w / 2 + 0.5)
    while gx <= math.floor(x1 - obj.w / 2 - 0.5):
        gy = math.ceil(y0 + obj.d / 2 + 0.5)
        while gy <= math.floor(y1 - obj.d / 2 - 0.5):
            x = float(gx)
            y = float(gy)
            if robot_ok(scene, x, y):
                ok = True
                for o in scene.objects():
                    if o.name == obj.name:
                        continue
                    need = req + (2.0 if o.h > 5 or obj.h > 5 else 0.0)
                    if abs(x - o.x) < (obj.w + o.w) / 2 + need and abs(y - o.y) < (obj.d + o.d) / 2 + need:
                        ok = False
                for ax, ay, aw, ad in avoids:
                    if abs(x - ax) < (obj.w + aw) / 2 + 1.5 and abs(y - ay) < (obj.d + ad) / 2 + 1.5:
                        ok = False
                if ok:
                    dist = (x - obj.x) * (x - obj.x) + (y - obj.y) * (y - obj.y)
                    if dist < bestd:
                        bestd = dist
                        best = (x, y)
            gy += 1
        gx += 1
    return best

def robot_ok(scene, x, y):
    return x >= scene.bounds()[0] and x <= scene.bounds()[2] and y >= scene.bounds()[1] and y <= scene.bounds()[3]

def find_spot(scene, obj, avoids):
    spot = scan(scene, obj, avoids, 2.0)
    if spot is None:
        spot = scan(scene, obj, avoids, 1.0)
    return spot

def clear_area(scene, robot, cx, cy, w, d, skip, avoids):
    for name in [o.name for o in scene.objects()]:
        if name in skip:
            continue
        o = scene.get(name)
        extra = 6.0 if o.h > 5 else 2.0
        if abs(o.x - cx) < (o.w + w) / 2 + extra and abs(o.y - cy) < (o.d + d) / 2 + extra:
            spot = find_spot(scene, o, avoids)
            if spot is not None:
                robot.move(scene.get(name), spot[0], spot[1])

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
    for name, tx, ty, ew, ed, yaw in infos:
        skip = [box.name, name] + placed + [p.name for p in pens]
        clear_area(scene, robot, tx, ty, ew, ed, skip, slots)
        pen = scene.get(name)
        clear_area(scene, robot, pen.x, pen.y, pen.w, pen.d, [box.name, name] + [p.name for p in pens], slots)
        clear_area(scene, robot, tx, ty, ew, ed, skip, slots)
        robot.move(scene.get(name), tx, ty, yaw)
        placed.append(name)
    robot.home()
