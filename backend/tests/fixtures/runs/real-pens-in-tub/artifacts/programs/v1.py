def run(scene, robot):
    tub = scene.get("white plastic tub")
    for pen in scene.of_kind("pen"):
        if scene.is_inside(pen, tub):
            continue
        robot.pick(scene.get(pen.name))
        robot.place_in(scene.get(tub.name))
