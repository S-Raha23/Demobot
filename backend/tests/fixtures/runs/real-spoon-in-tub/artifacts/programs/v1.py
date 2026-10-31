def run(scene, robot):
    spoon = scene.of_kind("spoon")[0]
    tubs = [c for c in scene.containers() if c.kind == "tub"]
    tub = tubs[0] if tubs else scene.containers()[0]
    if scene.is_inside(scene.get(spoon.name), scene.get(tub.name)):
        return
    robot.pick(scene.get(spoon.name))
    robot.place_in(scene.get(tub.name))
