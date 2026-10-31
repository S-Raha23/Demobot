def run(scene, robot):
    for o in scene.objects():
        log(o.name + " " + str(round(o.x,1)) + "," + str(round(o.y,1)) + " " + str(round(o.w,1)) + "x" + str(round(o.d,1)) + " h" + str(round(o.h,1)) + " yaw" + str(round(o.yaw,1)))
    log(str(scene.bounds()))
