def run(scene, robot):
    for pen in scene.of_kind("pen"):
        cup = scene.get("white cup")
        cur = scene.get(pen.name)
        if scene.is_inside(cur, cup):
            continue
        robot.pick(cur)
        robot.place_in(scene.get(cup.name))
