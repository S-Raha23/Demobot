def run(scene, robot):
    mug = scene.of_kind("mug")[0]
    box = scene.of_kind("box")[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(mug if item.kind == "pen" else box)
