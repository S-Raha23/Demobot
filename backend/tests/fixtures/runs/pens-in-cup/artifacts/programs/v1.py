def run(scene, robot):
    pens = scene.of_kind("pen")
    teal = [p for p in pens if "teal" in p.name]
    if teal:
        pens = teal
    for pen in pens:
        cup = scene.get("white cup")
        cur = scene.get(pen.name)
        if scene.is_inside(cur, cup):
            continue
        robot.pick(cur)
        robot.place_in(scene.get(cup.name))
