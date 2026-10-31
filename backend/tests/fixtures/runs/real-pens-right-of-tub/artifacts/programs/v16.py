def run(scene, robot):
    balls = scene.of_kind("tennis ball")
    tub = scene.get("white tub")
    if any(not scene.is_inside(b, tub) for b in balls):
        robot.move(scene.get("white tub"), *scene.free_spot(size=(14, 14), clearance=4))
    for ball in scene.of_kind("tennis ball"):
        tub = scene.get("white tub")
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    robot.home()
