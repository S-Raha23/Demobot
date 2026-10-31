def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    behind = [p for p in pens if p.y < box.y]
    if behind:
        pen = min(behind, key=lambda p: abs(p.x - box.x))
    else:
        named = [p for p in pens if p.name == "back teal pen"]
        moved = [p for p in scene.with_role("moved") if p.kind == "pen"]
        if named:
            pen = named[0]
        elif moved:
            pen = moved[0]
        else:
            pen = min(pens, key=lambda p: p.y)
    gap = 2.0
    tx = box.x - box.w / 2 - gap - pen.w / 2
    ty = box.y
    skip = {box.name, pen.name}
    for o in scene.objects():
        if o.name in skip:
            continue
        if abs(o.x - tx) < (o.w + pen.w) / 2 + 4 and abs(o.y - ty) < (o.d + pen.d) / 2 + 4:
            robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[(tx, ty, pen.w + 4, pen.d + 4)]))
            box = scene.get(box.name)
            pen = scene.get(pen.name)
            tx = box.x - box.w / 2 - gap - pen.w / 2
            ty = box.y
    if robot.can_reach(tx, ty):
        log("placing pen left of box")
    robot.pick(scene.get(pen.name))
    robot.place_next_to(scene.get(box.name), "left_of", gap=gap)
