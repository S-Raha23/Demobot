def run(scene, robot):
    log(str(scene.bounds()))
    for o in scene.objects():
        log(o.name + " x=" + str(o.x) + " y=" + str(o.y) + " w=" + str(o.w) + " d=" + str(o.d) + " h=" + str(o.h) + " yaw=" + str(o.yaw))
