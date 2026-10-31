def run(scene, robot):
    box = scene.containers()[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(box)
    robot.place_in(box)
