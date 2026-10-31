def run(scene, robot):
    box = scene.get("white box")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(scene.get(ball.name), scene.get("white box")):
            continue
        b = scene.get(ball.name)
        bx = scene.get("white box")
        blockers = []
        for o in scene.objects():
            if o.name in (b.name, bx.name):
                continue
            m = 7.0 if o.h > 5 else 2.0
            if abs(o.x - b.x) < (o.w + b.w) / 2 + m and abs(o.y - b.y) < (o.d + b.d) / 2 + m:
                blockers.append(o)
        for o in sorted(blockers, key=lambda q: -q.h):
            cur = scene.get(o.name)
            spot = scene.free_spot(size=(cur.w, cur.d), clearance=3, avoid=[(bx.x, bx.y, bx.w + 4, bx.d + 4), (b.x, b.y, b.w + 8, b.d + 8)])
            robot.move(cur, spot[0], spot[1])
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white box"))
    robot.home()
