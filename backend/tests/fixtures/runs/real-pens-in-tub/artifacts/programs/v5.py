def run(scene, robot):
    tub = scene.get("white plastic tub")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get(tub.name))
