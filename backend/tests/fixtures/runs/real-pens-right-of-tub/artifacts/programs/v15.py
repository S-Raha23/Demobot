def run(scene, robot):
    for ball in scene.of_kind("tennis ball"):
        tub = scene.get("white tub")
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        tub = scene.get("white tub")
        robot.place_at(tub.x, tub.y)
    robot.home()
