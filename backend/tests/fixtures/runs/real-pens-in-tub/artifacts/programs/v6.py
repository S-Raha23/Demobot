def run(scene, robot):
    tub = scene.get("white plastic tub")
    balls = [b for b in scene.of_kind("tennis ball") if not scene.is_inside(b, tub)]
    if balls:
        x0, y0, x1, y1 = scene.bounds()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if abs(tub.x - cx) > 15 or abs(tub.y - cy) > 8 or not robot.can_reach(tub.x, tub.y):
            spot = scene.free_spot(size=(tub.w, tub.d), clearance=2)
            robot.move(scene.get(tub.name), spot[0], spot[1])
            tub = scene.get(tub.name)
    for ball in balls:
        if scene.is_inside(scene.get(ball.name), scene.get(tub.name)):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get(tub.name))
