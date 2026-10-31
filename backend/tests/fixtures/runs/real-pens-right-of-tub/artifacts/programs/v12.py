def run(scene, robot):
    balls = scene.of_kind("tennis ball")
    for ball in balls:
        tub = scene.get("white tub")
        if scene.is_inside(ball, tub):
            continue
        bx, by = ball.x, ball.y
        robot.pick(scene.get("white tub"))
        robot.place_at(bx, by)
    robot.home()
