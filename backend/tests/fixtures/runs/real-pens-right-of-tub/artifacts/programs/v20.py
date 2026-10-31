def run(scene, robot):
    for ball in scene.of_kind("tennis ball"):
        tub = scene.get("white tub")
        if scene.is_inside(ball, tub):
            continue
        tub_f = scene.get("white tub")
        ball_f = scene.get(ball.name)
        for o in list(scene.objects()):
            if o.name in [ball.name, tub_f.name]:
                continue
            o_f = scene.get(o.name)
            if scene.distance(o_f, tub_f) < 14 or scene.distance(o_f, ball_f) < 12:
                robot.move(o_f, *scene.free_spot(size=(o_f.w, o_f.d), clearance=3, avoid=[(tub_f.x, tub_f.y, tub_f.w + 10, tub_f.d + 10), (ball_f.x, ball_f.y, ball_f.w + 10, ball_f.d + 10)]))
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    robot.home()
