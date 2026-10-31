def run(scene, robot):
    tub = scene.get("white tub")
    targets = []
    for obj in scene.of_kind("pen") + scene.with_role("moved"):
        if obj.name not in targets:
            targets.append(obj.name)
    log("targets: " + str(targets))
    for name in targets:
        cur = scene.get(name)
        dst = scene.get(tub.name)
        if scene.is_inside(cur, dst):
            continue
        robot.pick(cur)
        robot.place_in(scene.get(tub.name))
