def run(scene, robot):
    tub = scene.get("white tub")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    tub = scene.get("white tub")
    zone_x = tub.x + tub.w / 2 + 9
    zone = (zone_x, tub.y, 18, tub.d + 8)
    avoids = [zone]
    for p in scene.of_kind("pen"):
        avoids.append((p.x, p.y, p.w + 14, p.d + 14))
    for o in scene.objects():
        if o.name == tub.name or o.kind in ("pen", "tennis ball"):
            continue
        fresh = scene.get(o.name)
        if abs(fresh.x - zone_x) < (fresh.w + 18) / 2 + 2 and abs(fresh.y - tub.y) < (fresh.d + tub.d + 8) / 2 + 2:
            robot.move(fresh, *scene.free_spot(size=(fresh.w, fresh.d), clearance=3, avoid=avoids))
    for pen in scene.of_kind("pen"):
        tub = scene.get("white tub")
        fresh = scene.get(pen.name)
        if fresh.x > tub.x + tub.w / 2 and abs(fresh.y - tub.y) < tub.d / 2 + 4:
            continue
        robot.pick(scene.get(pen.name))
        robot.place_next_to(scene.get("white tub"), "right_of", gap=2.0)
    robot.home()
