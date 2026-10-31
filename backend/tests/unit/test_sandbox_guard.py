"""The AST guard rejects malicious programs (M2 acceptance: 15 snippets)."""

import pytest

from demobot.program.sandbox import GuardError, guard

OK = "def run(scene, robot):\n    pass\n"

MALICIOUS = {
    "import_os": "import os\n" + OK,
    "from_import": "from subprocess import run as r\n" + OK,
    "dunder_class": "def run(scene, robot):\n    x = ().__class__.__bases__[0].__subclasses__()\n",
    "private_attr": "def run(scene, robot):\n    robot._sim.client\n",
    "open_file": "def run(scene, robot):\n    open('/etc/passwd').read()\n",
    "eval": "def run(scene, robot):\n    eval('1+1')\n",
    "exec": "def run(scene, robot):\n    exec('import os')\n",
    "getattr": "def run(scene, robot):\n    getattr(robot, '_skills')\n",
    "dunder_import": "def run(scene, robot):\n    __import__('os').system('ls')\n",
    "globals": "def run(scene, robot):\n    globals()['x'] = 1\n",
    "format_escape": "def run(scene, robot):\n    '{0.__class__}'.format(scene)\n",
    "try_swallow": "def run(scene, robot):\n    try:\n        robot.pick(scene.get('a'))\n    except Exception:\n        pass\n",
    "class_def": "class X:\n    pass\n" + OK,
    "module_code": "x = scene.get('pen')\n" + OK,
    "global_stmt": "def run(scene, robot):\n    global z\n    z = 1\n",
    "type_builtin": "def run(scene, robot):\n    type(scene).mro()\n",
    "with_stmt": "def run(scene, robot):\n    with x:\n        pass\n",
    "no_run": "def go(scene, robot):\n    pass\n",
    "bad_signature": "def run(robot):\n    pass\n",
    "print": "def run(scene, robot):\n    print('hi')\n",
}


@pytest.mark.parametrize("name", sorted(MALICIOUS))
def test_malicious_snippets_are_rejected(name: str) -> None:
    with pytest.raises(GuardError) as err:
        guard(MALICIOUS[name])
    assert err.value.problems and all(p for p in err.value.problems)


def test_at_least_fifteen_snippets() -> None:
    assert len(MALICIOUS) >= 15


def test_problems_name_the_line_and_the_fix() -> None:
    with pytest.raises(GuardError) as err:
        guard(MALICIOUS["try_swallow"])
    assert any("line 2" in p and "surface" in p for p in err.value.problems)
    with pytest.raises(GuardError) as err:
        guard(MALICIOUS["print"])
    assert any("log()" in p for p in err.value.problems)


def test_helpers_constants_and_comprehensions_are_allowed() -> None:
    guard(
        "import math\nGAP = 2.5\nNAMES = ['a', 'b']\n\n"
        "def helper(o):\n    return [n for n in NAMES if n != o.name]\n\n"
        "def run(scene, robot):\n"
        "    xs = sorted(scene.objects(), key=lambda o: o.x)\n"
        "    total = sum(o.w for o in xs) + GAP * math.sqrt(4)\n"
        "    log(f'{len(xs)} objects, {total:.1f} cm')\n"
        "    i = 0\n    while i < 3:\n        i += 1\n"
    )
