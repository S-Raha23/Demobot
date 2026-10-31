def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    temp = scene.free_spot(size=(a.w, a.d), clearance=3)
    robot.move(a, *temp)
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
