def run(scene, robot):
    spoons = scene.of_kind("spoon")
    if spoons:
        spoon = spoons[0]
    else:
        spoon = scene.with_role("moved")[0]
    tubs = scene.containers()
    if tubs:
        tub = tubs[0]
    else:
        tub = scene.of_kind("tub")[0]
    if scene.is_inside(spoon, tub):
        return
    robot.pick(spoon)
    robot.place_in(tub)
