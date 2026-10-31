def run(scene, robot):
    for o in scene.objects():
        log(f"{o.name} x={o.x} y={o.y} w={o.w} d={o.d} h={o.h} yaw={o.yaw}")
