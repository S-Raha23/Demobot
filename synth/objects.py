"""The desk-item catalogue for synthetic demos: the human's real objects (sizes in cm, colours),
so the pipeline is tuned for what the real clips will show: a white square plastic box (the
container), two teal pens, a teal box cutter, a small glue bottle, a yellow tennis ball, a steel
spoon, and a mug or cup as the second container for sorting."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / "assets" / "textures"


@dataclass(frozen=True)
class Item:
    kind: str
    shape: str  # box | cylinder | sphere
    w: float
    d: float
    h: float
    colors: tuple[tuple[str, str], ...]  # (colour word, hex)
    container: bool = False
    texture_prompt: str = ""

    def texture(self, color_word: str) -> str | None:
        p = TEXTURES / f"{self.kind.replace(' ', '_')}_{color_word}.png"
        return str(p) if p.exists() else None


CATALOGUE: dict[str, Item] = {
    "box": Item("box", "box", 13, 13, 6.5, (("white", "#eeeeea"),), container=True,
                texture_prompt="the inside of an empty white square plastic storage box, seen from directly above"),
    "mug": Item("mug", "cylinder", 8.5, 8.5, 9.5, (("white", "#ecebe6"), ("blue", "#3b6fd6")), container=True,
                texture_prompt="the inside of an empty ceramic mug, seen from directly above"),
    "pen": Item("pen", "box", 14.5, 1.2, 1.2, (("teal", "#178f8f"),),
                texture_prompt="a teal ballpoint pen lying flat, seen from directly above"),
    "box cutter": Item("box cutter", "box", 15, 2.6, 1.8, (("teal", "#1a9a95"),),
                       texture_prompt="a teal plastic box cutter (utility knife) lying flat, blade retracted, seen from directly above"),
    "glue bottle": Item("glue bottle", "cylinder", 3.8, 3.8, 9.0, (("white", "#f2f0e8"),),
                        texture_prompt="the top of a small white glue bottle with an orange cap, seen from directly above"),
    "tennis ball": Item("tennis ball", "sphere", 6.7, 6.7, 6.7, (("yellow", "#d9e43a"),),
                        texture_prompt="the fuzzy yellow-green felt surface of a tennis ball with its white curved seam"),
    "spoon": Item("spoon", "box", 15.5, 3.4, 1.0, (("steel", "#b9bec4"),),
                  texture_prompt="a stainless steel teaspoon lying flat, seen from directly above"),
}  # fmt: skip

CONTAINERS = ("box", "mug")
SMALL_ITEMS = ("pen", "box cutter", "glue bottle", "tennis ball", "spoon")
