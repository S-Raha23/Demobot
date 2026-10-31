def run(scene, robot):
    moved = scene.with_role("moved")
    if len(moved) == 2:
        a, b = moved[0], moved[1]
    else:
        a = scene.of_kind("box cutter")[0]
        b = scene.of_kind("glue bottle")[0]
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    side = max(a.w, a.d, b.w, b.d) + 2
    buf_x, buf_y = scene.free_spot(size=(side, side), clearance=3)
    robot.move(a, buf_x, buf_y)
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
