def run(scene, robot):
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    log("cutter " + str((ax, ay, a.w, a.d, a.h)) + " glue " + str((bx, by, b.w, b.d, b.h)))
    temp = scene.free_spot(size=(a.w, a.d), clearance=2)
    log("temp cutter " + str(temp))
    robot.move(scene.get(a.name), temp[0], temp[1])
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
