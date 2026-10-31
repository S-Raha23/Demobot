def run(scene, robot):
    tub = scene.get("white tub")
    balls = scene.of_kind("tennis ball")
    if any(not scene.is_inside(b, tub) for b in balls):
        tub = scene.get("white tub")
        avoid = [(tub.x, tub.y, 34, 34)]
        for o in scene.objects():
            if o.name == tub.name or o.kind == "tennis ball":
                continue
            t = scene.get("white tub")
            if scene.distance(o, t) < 22:
                robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=avoid))
    for ball in scene.of_kind("tennis ball"):
        tub = scene.get("white tub")
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    robot.home()
