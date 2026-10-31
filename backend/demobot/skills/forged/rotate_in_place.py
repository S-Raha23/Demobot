import math

def norm_yaw(yaw):
    return (float(yaw) + 180.0) % 360.0 - 180.0

def ang_err(a, b):
    return abs(norm_yaw(a - b))

def rotate_in_place(robot, scene, obj, dyaw_deg):
    dyaw = norm_yaw(dyaw_deg)
    if abs(dyaw) < 0.001:
        return
    fresh = scene.get(obj.name)
    x0, y0, z0, yaw0 = scene.pose(fresh)
    target = norm_yaw(yaw0 + dyaw)
    log(f"rotate_in_place {fresh.name} at ({x0:.1f},{y0:.1f}) yaw {yaw0:.1f} -> {target:.1f}")
    robot.pick(fresh)
    robot.place_at(x0, y0, yaw=target)
    robot.wait(0.4)
    fresh = scene.get(obj.name)
    x1, y1, z1, yaw1 = scene.pose(fresh)
    poserr = math.hypot(x1 - x0, y1 - y0)
    yawerr = ang_err(yaw1, target)
    log(f"rotate_in_place result poserr {poserr:.2f} yawerr {yawerr:.1f}")
    if poserr > 1.0 or yawerr > 5.0:
        corrected = norm_yaw(target + norm_yaw(target - yaw1))
        fresh = scene.get(obj.name)
        robot.pick(fresh)
        robot.place_at(x0, y0, yaw=corrected)
        robot.wait(0.4)
        fresh = scene.get(obj.name)
        x2, y2, z2, yaw2 = scene.pose(fresh)
        log(f"rotate_in_place corrected poserr {math.hypot(x2 - x0, y2 - y0):.2f} yawerr {ang_err(yaw2, target):.1f}")
