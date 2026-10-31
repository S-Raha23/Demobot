def run(scene, robot):
    box = scene.of_kind("box")[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(box)
