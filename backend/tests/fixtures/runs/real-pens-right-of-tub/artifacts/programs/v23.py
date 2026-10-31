def run(scene, robot):
    x0, y0, x1, y1 = scene.bounds()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    log(f"bounds {scene.bounds()} centre {cx} {cy}")
    tub = scene.get("white tub")
    for o in list(scene.objects()):
        if o.name in [tub.name] or o.kind == "tennis ball":
            continue
        if abs(o.x - cx) < (o.w + tub.w) / 2 + 4 and abs(o.y - cy) < (o.d + tub.d) / 2 + 4:
            robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[(cx, cy, tub.w + 6, tub.d + 6)]))
    robot.move(scene.get("white tub"), cx, cy)
    log(f"tub now {scene.get('white tub').x} {scene.get('white tub').y}")
    ball = scene.of_kind("tennis ball")[0]
    if not scene.is_inside(ball, scene.get("white tub")):
        robot.pick(scene.get(ball.name))
        t = scene.get("white tub")
        robot.place_at(t.x, t.y)
    robot.home()
