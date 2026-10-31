def run(scene, robot):
    for attempt in range(4):
        tub = scene.get("white tub")
        ball = scene.of_kind("tennis ball")[0]
        if scene.is_inside(ball, tub):
            break
        log(f"attempt {attempt}: ball at {ball.x}, {ball.y}, {ball.z}")
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    robot.home()
