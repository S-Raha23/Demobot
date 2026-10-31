Every pen into the container:
```python
def run(scene, robot):
    box = scene.containers()[0]
    for pen in scene.of_kind("pen"):
        if scene.is_inside(pen, box):
            continue
        robot.pick(pen)
        robot.place_in(box)
```

One item to the right of a reference, clearing the spot first:
```python
def blockers(scene, x, y, w, d, skip):
    return [
        o
        for o in scene.objects()
        if o.name not in skip
        and abs(o.x - x) < (o.w + w) / 2 + 4
        and abs(o.y - y) < (o.d + d) / 2 + 4
    ]


def run(scene, robot):
    ref = scene.get("white mug")
    item = scene.get("eraser")
    x = ref.x + ref.w / 2 + 2.5 + item.w / 2
    for b in blockers(scene, x, ref.y, item.w, item.d, [ref.name, item.name]):
        robot.move(
            b,
            *scene.free_spot(
                size=(b.w, b.d), clearance=3, avoid=[(x, ref.y, item.w + 4, item.d + 4)]
            ),
        )
    robot.pick(scene.get(item.name))
    robot.place_next_to(scene.get(ref.name), "right_of", gap=2.5)
```

Line the moved items up left to right in the middle of the work area:
```python
def run(scene, robot):
    items = scene.with_role("moved")
    x0, y0, x1, y1 = scene.bounds()
    y = (y0 + y1) / 2
    total = sum(o.w for o in items) + 4 * (len(items) - 1)
    x = (x0 + x1) / 2 - total / 2
    placed = []
    for item in items:
        cx = x + item.w / 2
        row = (cx, y, 2 * (x1 - x0), item.d + 2)
        for o in scene.objects():
            if (
                o.name != item.name
                and o.name not in placed
                and abs(o.x - cx) < (o.w + item.w) / 2 + 4
                and abs(o.y - y) < (o.d + item.d) / 2 + 4
            ):
                robot.move(o, *scene.free_spot(size=(o.w, o.d), clearance=3, avoid=[row]))
        robot.move(scene.get(item.name), cx, y)
        placed.append(item.name)
        x += item.w + 4
```

Swap two items through a free spot:
```python
def run(scene, robot):
    a, b = scene.get("eraser"), scene.get("matchbox")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    side = max(a.w, a.d, b.w, b.d) + 2
    robot.move(a, *scene.free_spot(size=(side, side), clearance=3))
    robot.move(scene.get(b.name), ax, ay)
    robot.move(scene.get(a.name), bx, by)
```
