import math

def norm(a):
    return (float(a) + 180.0) % 360.0 - 180.0

def target_obj(scene):
    objs = [o for o in scene.objects() if "box cutter" in o.name.lower()]
    if not objs:
        objs = scene.with_role("moved")
    if not objs:
        return None
    return objs[0]

def check(robot, scene, skill, dyaw):
    obj = target_obj(scene)
    if obj is None:
        return "skip"
    x0, y0, yaw0 = obj.x, obj.y, obj.yaw
    before = {o.name: (o.x, o.y, o.yaw) for o in scene.objects()}
    skill(robot, scene, obj, dyaw)
    fresh = scene.get(obj.name)
    x1, y1, z1, yaw1 = fresh.x, fresh.y, fresh.z, fresh.yaw
    target = norm(yaw0 + dyaw)
    yawerr = abs(norm(yaw1 - target))
    poserr = math.hypot(x1 - x0, y1 - y0)
    assert poserr <= 2.0, f"moved {poserr:.2f} cm, limit 2"
    assert yawerr <= 10.0, f"yaw err {yawerr:.1f}, got {yaw1:.1f} want {target:.1f}"
    assert z1 > 0.2 and z1 < 3.0, f"not upright/on table z={z1:.2f}"
    for name, p in before.items():
        if name == obj.name:
            continue
        q = scene.get(name)
        d = math.hypot(q.x - p[0], q.y - p[1])
        assert d <= 1.0, f"other object {name} displaced {d:.2f} cm"

def test_rotate_90(robot, scene, skill):
    return check(robot, scene, skill, 90)

def test_rotate_minus_90(robot, scene, skill):
    return check(robot, scene, skill, -90)

def test_rotate_45(robot, scene, skill):
    return check(robot, scene, skill, 45)

def test_rotate_180(robot, scene, skill):
    return check(robot, scene, skill, 180)
