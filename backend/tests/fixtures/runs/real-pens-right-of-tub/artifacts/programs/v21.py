def run(scene, robot):
    tub = scene.get("white tub")
    ball = scene.of_kind("tennis ball")[0]
    if scene.is_inside(ball, tub):
        return
    robot.move(scene.get("white tub"), *scene.free_spot(size=(tub.w, tub.d), clearance=4))
    robot.pick(scene.get(ball.name))
    robot.place_in(scene.get("white tub"))
    robot.home()
