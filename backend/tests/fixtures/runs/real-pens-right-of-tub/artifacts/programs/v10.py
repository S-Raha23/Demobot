def run(scene, robot):
    tub = scene.get("white tub")
    for ball in scene.of_kind("tennis ball"):
        fresh_tub = scene.get("white tub")
        if scene.is_inside(ball, fresh_tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    robot.home()
