def run(scene, robot):
    items = scene.with_role("moved")
    a, b = items[0], items[1]
    # Park the smaller item first: a small footprint leaves more usable free spots.
    parked, other = (a, b) if a.w * a.d <= b.w * b.d else (b, a)
    px, py = parked.x, parked.y
    ox, oy = other.x, other.y
    temp = scene.free_spot(size=(parked.w, parked.d), clearance=3)
    log("Parking " + parked.name + " temporarily at " + str(temp))
    robot.move(scene.get(parked.name), temp[0], temp[1])
    robot.move(scene.get(other.name), px, py)
    robot.move(scene.get(parked.name), ox, oy)
