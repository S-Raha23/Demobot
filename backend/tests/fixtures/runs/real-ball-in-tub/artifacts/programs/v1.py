def run(scene, robot):
    ball = scene.get("green ball")
    box = scene.get("white box")
    if scene.is_inside(ball, box):
        return
    robot.pick(ball)
    robot.place_in(box)
