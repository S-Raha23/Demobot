def run(scene, robot):
    tub = scene.get("white tub")
    for ball in scene.of_kind("tennis ball"):
        if scene.is_inside(ball, tub):
            continue
        robot.pick(scene.get(ball.name))
        robot.place_in(scene.get("white tub"))
    for pen in scene.of_kind("pen"):
        tub = scene.get("white tub")
        if pen.x > tub.x + tub.w / 2 and abs(pen.y - tub.y) < tub.d / 2 + 3:
            continue
        robot.pick(scene.get(pen.name))
        robot.place_next_to(scene.get("white tub"), "right_of", gap=2.0)
    robot.home()
