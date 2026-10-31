def run(scene, robot):
    box = scene.containers()[0]
    for pen in scene.of_kind("pen"):
        if scene.is_inside(pen, box):
            continue
        robot.pick(pen)
        robot.place_in(box)
    robot.home()
