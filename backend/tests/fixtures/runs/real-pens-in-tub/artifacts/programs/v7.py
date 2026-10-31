def run(scene, robot):
    tub = scene.get("white plastic tub")
    balls = [b for b in scene.of_kind("tennis ball") if not scene.is_inside(b, tub)]
    if balls:
        x0, y0, x1, y1 = scene.bounds()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if abs(tub.x - cx) > 15 or abs(tub.y - cy) > 8 or not robot.can_reach(tub.x, tub.y):
            tx = min(max(tub.x, cx - 10), cx + 10)
            ty = min(max(tub.y, cy - 6), cy + 6)
            for o in scene.objects():
                if o.name == tub.name:
                    continue
                if abs(o.x - tx) < (o.w + tub.w) / 2 + 2 and abs(o.y - ty) < (o.d + tub.d) / 2 + 2:
                    robot.move(scene.get(o.name), *scene.free_spot(size=(o.w, o.d), clearance=2, avoid=[(tx, ty, tub.w + 4, tub.d + 4)]))
            robot.move(scene.get(tub.name), tx, ty)
    for ball in balls:
        if scene.is_inside(scene.get(ball.name), scene.get(tub.name)):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get(tub.name))
