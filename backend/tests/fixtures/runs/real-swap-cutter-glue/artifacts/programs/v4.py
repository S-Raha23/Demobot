def run(scene, robot):
    a = scene.of_kind("box cutter")[0]
    b = scene.of_kind("glue bottle")[0]
    ax, ay, ayaw = a.x, a.y, a.yaw
    bx, by, byaw = b.x, b.y, b.yaw
    buf_x, buf_y = scene.free_spot(size=(b.w, b.d), clearance=2)
    robot.move(scene.get(b.name), buf_x, buf_y)
    robot.move(scene.get(a.name), bx, by, yaw=ayaw)
    robot.move(scene.get(b.name), ax, ay, yaw=byaw)
