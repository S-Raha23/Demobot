def run(scene, robot):
    for o in scene.objects():
        log(o.name + " " + str(round(o.x,1)) + "," + str(round(o.y,1)) + " w" + str(round(o.w,1)) + " d" + str(round(o.d,1)) + " h" + str(round(o.h,1)) + " yaw" + str(round(o.yaw,1)))
    log("bounds " + str(scene.bounds()))
    p = scene.free_spot(size=(13, 2), clearance=2)
    log("spot13x2 " + str(p))
    p2 = scene.free_spot(size=(3, 3), clearance=2)
    log("spot3x3 " + str(p2))
