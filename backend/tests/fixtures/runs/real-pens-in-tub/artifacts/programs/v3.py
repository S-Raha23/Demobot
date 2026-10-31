def run(scene, robot):
    for o in scene.objects():
        log(f"{o.name} kind={o.kind} role={o.role} x={o.x} y={o.y} w={o.w} d={o.d} h={o.h}")
    log(f"bounds={scene.bounds()}")
