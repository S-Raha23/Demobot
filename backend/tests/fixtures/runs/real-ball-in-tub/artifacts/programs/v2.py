def run(scene, robot):
    ball = scene.with_role("moved")[0]
    box = scene.containers()[0]
    if scene.is_inside(ball, box):
        return
    robot.pick(scene.get(ball.name))
    robot.place_in(scene.get(box.name))
