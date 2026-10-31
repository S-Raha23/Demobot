def run(scene, robot):
    ball = scene.get("yellow tennis ball")
    tub = scene.get("white plastic tub")
    if scene.is_inside(ball, tub):
        return
    robot.pick(scene.get(ball.name))
    robot.place_in(scene.get(tub.name))
