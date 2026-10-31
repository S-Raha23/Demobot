def run(scene, robot):
    for o in scene.objects():
        log(o.name + " kind=" + o.kind + " role=" + o.role + " pos=" + str((round(o.x,1), round(o.y,1))) + " size=" + str((round(o.w,1), round(o.d,1), round(o.h,1))) + " yaw=" + str(round(o.yaw,1)))
    log("bounds " + str(scene.bounds()))
    a = scene.get("light blue box cutter")
    b = scene.get("white glue bottle")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    temp = scene.free_spot(size=(a.w, a.d), clearance=2)
    log("temp cutter " + str(temp))
    robot.move(scene.get(a.name), temp[0], temp[1])
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
