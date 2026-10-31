def run(scene, robot):
    for ball in scene.of_kind("tennis ball"):
        for attempt in range(4):
            tub = scene.get("white tub")
            cur = scene.get(ball.name)
            if scene.is_inside(cur, tub):
                break
            robot.pick(cur)
            robot.place_in(scene.get("white tub"))
    robot.home()
