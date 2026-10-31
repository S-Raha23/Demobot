def run(scene, robot):
    balls = scene.of_kind("tennis ball")
    if balls:
        ball = balls[0]
    else:
        ball = scene.get("tennis ball")
    tubs = scene.containers()
    if tubs:
        tub = tubs[0]
    else:
        tub = scene.get("white tub")
    if scene.is_inside(ball, tub):
        return
    robot.pick(scene.get(ball.name))
    robot.place_in(scene.get(tub.name))
