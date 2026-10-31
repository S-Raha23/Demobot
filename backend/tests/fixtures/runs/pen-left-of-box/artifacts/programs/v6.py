def run(scene, robot):
    box = scene.get("white box")
    pens = scene.of_kind("pen")
    named = [p for p in pens if p.name == "back teal pen"]
    moved = [p for p in scene.with_role("moved") if p.kind == "pen"]
    if named:
        pen = named[0]
    elif moved:
        pen = moved[0]
    else:
        behind = [p for p in pens if p.y < box.y]
        pen = min(behind, key=lambda p: abs(p.x - box.x)) if behind else pens[0]
    gap = 2.0
    tx = box.x + box.w / 2 + gap + pen.w / 2
    ty = box.y
    skip = {box.name, pen.name}
    for o in list(scene.objects()):
        if o.name in skip:
            continue
        cur = scene.get(o.name)
        if abs(cur.x - tx) < (cur.w + pen.w) / 2 + 2 and abs(cur.y - ty) < (cur.d + pen.d) / 2 + 2:
            robot.move(cur, *scene.free_spot(size=(cur.w, cur.d), clearance=2, avoid=[(tx, ty, pen.w + 4, pen.d + 4)]))
    box = scene.get(box.name)
    pen = scene.get(pen.name)
    log("moving " + pen.name + " right of " + box.name)
    robot.pick(pen)
    robot.place_next_to(box, "right_of", gap=gap)
