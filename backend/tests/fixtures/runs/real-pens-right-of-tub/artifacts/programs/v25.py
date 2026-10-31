def run(scene, robot):
    tub = scene.get("white tub")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    tub = scene.get("white tub")
    zone_x = tub.x + tub.w / 2 + 8
    zone = (zone_x, tub.y, 20, tub.d + 10)
    for o in scene.objects():
        if o.name == tub.name or o.kind in ("pen", "tennis ball"):
            continue
        if abs(o.x - zone_x) < (o.w + 20) / 2 + 3 and abs(o.y - tub.y) < (o.d + tub.d + 10) / 2 + 3:
            robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[zone]))
    for pen in scene.of_kind("pen"):
        tub = scene.get("white tub")
        fresh = scene.get(pen.name)
        if fresh.x > tub.x + tub.w / 2 and abs(fresh.y - tub.y) < tub.d / 2 + 4:
            continue
        robot.pick(scene.get(pen.name))
        robot.place_next_to(scene.get("white tub"), "right_of", gap=2.0)
    robot.home()
