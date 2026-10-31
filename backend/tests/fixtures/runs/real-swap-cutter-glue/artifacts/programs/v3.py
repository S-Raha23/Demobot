def run(scene, robot):
    log(f"bounds={scene.bounds()}")
    for o in scene.objects():
        log(f"{o.name} kind={o.kind} role={o.role} x={o.x} y={o.y} w={o.w} d={o.d} h={o.h} yaw={o.yaw} reach={robot.can_reach(o.x, o.y)}")
