def run(scene, robot):
    ref = scene.with_role("reference")[0]
    item = scene.with_role("moved")[0]
    robot.pick(item)
    robot.place_next_to(scene.get(ref.name), "left_of", gap=2.5)
