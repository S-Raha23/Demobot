def run(scene, robot):
    spoon = scene.get("silver spoon")
    tub = scene.get("white plastic tub")
    if scene.is_inside(spoon, tub):
        return
    robot.pick(scene.get(spoon.name))
    robot.place_in(scene.get(tub.name))
