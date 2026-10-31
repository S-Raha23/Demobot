def run(scene, robot):
    box = scene.get("white box")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(scene.get(ball.name), box):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white box"))
    robot.home()
