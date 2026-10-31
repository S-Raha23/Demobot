def run(scene, robot):
    a = scene.of_kind("box cutter")[0]
    b = scene.of_kind("glue bottle")[0]
    ax, ay, ayaw = a.x, a.y, a.yaw
    bx, by, byaw = b.x, b.y, b.yaw
    log(f"swap {a.name} ({ax},{ay}) with {b.name} ({bx},{by})")
    buf_x, buf_y = scene.free_spot(size=(a.w, a.d), clearance=2)
    robot.move(scene.get(a.name), buf_x, buf_y)
    robot.move(scene.get(b.name), ax, ay, yaw=byaw)
    robot.move(scene.get(a.name), bx, by, yaw=ayaw)
