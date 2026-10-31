def run(scene, robot):
    balls = scene.of_kind("tennis ball")
    if balls:
        ball = balls[0]
    else:
        ball = scene.with_role("moved")[0]
    tub = scene.containers()[0]
    for c in scene.containers():
        if "tub" in c.kind.lower() or "white tub" in c.name.lower():
            tub = c
            break
    if scene.is_inside(ball, tub):
        return
    robot.pick(ball)
    robot.place_in(tub)
