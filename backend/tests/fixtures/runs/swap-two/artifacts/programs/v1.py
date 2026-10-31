def run(scene, robot):
    items = scene.with_role("moved")
    a = items[0]
    b = items[1]
    if a.w * a.d > b.w * b.d:
        a, b = b, a
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    tx, ty = scene.free_spot(size=(a.w, a.d), clearance=3)
    robot.move(a, tx, ty)
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
