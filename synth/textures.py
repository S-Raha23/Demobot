"""Generate the synthetic objects' textures once with Muse Image (through the gateway, cached)
and save them to assets/textures/ (committed). Material swatches, not product photos: a texture
is stretched over a whole stand-in, so it must fill the frame edge to edge.

    uv run python -m synth.textures
"""

import asyncio
import base64
import io
import sys
import time
from typing import Any

from PIL import Image

from demobot import gateway
from demobot.config import settings
from demobot.events import RunContext
from demobot.providers import client, dump
from synth.objects import TEXTURES

SWATCH = (
    "A seamless, perfectly flat, evenly lit close-up texture swatch of {what}, filling the entire "
    "square frame edge to edge, seen straight on, no object outline, no background, no shadows, "
    "no text."
)
JOBS = {
    "pen_teal": "glossy teal plastic, like the barrel of a ballpoint pen",
    "box_cutter_teal": "matte teal plastic with a fine grip texture, like a box cutter handle",
    "glue_bottle_white": "smooth white plastic, like a small glue bottle",
    "tennis_ball_yellow": "fuzzy yellow-green tennis-ball felt with a curved white seam",
    "spoon_steel": "brushed stainless steel with soft reflections, like a teaspoon",
    "box_white": "white semi-matte plastic, like a storage box",
    "mug_white": "glazed white ceramic, like a coffee mug",
    "desk_wood": "a light oak wooden desk top with a gentle grain",
}
SIZE = 512


def _call(prompt: str) -> gateway.Call:
    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        resp = (
            await client("meta")
            .with_options(timeout=timeout)
            .images.generate(model=settings.model_image, prompt=prompt, n=1)
        )
        return dump(resp), 0.01, {"images": 1}

    return call


async def make(name: str, what: str) -> None:
    prompt = SWATCH.format(what=what)
    raw = await gateway.cached_call(
        ctx=RunContext(run_id=None, mode="dev"),
        purpose=f"texture:{name}",
        provider="meta",
        model=settings.model_image,
        request={"prompt": prompt, "kind": "texture"},
        estimate_usd=0.02,
        call=_call(prompt),
        validate=gateway.passthrough,
    )
    b64 = raw["data"][0]["b64_json"]
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    side = min(img.size)
    img = img.crop(((img.width - side) // 2, (img.height - side) // 2, (img.width + side) // 2,
                    (img.height + side) // 2)).resize((SIZE, SIZE), Image.LANCZOS)  # fmt: skip
    TEXTURES.mkdir(parents=True, exist_ok=True)
    img.save(TEXTURES / f"{name}.png")
    print(f"{name}: saved", file=sys.stderr)


async def main() -> None:
    t0 = time.monotonic()
    names = sys.argv[1:] or list(JOBS)
    for name in names:  # sequential: each takes 10–25 s
        await make(name, JOBS[name])
    print(f"{len(names)} textures in {time.monotonic() - t0:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
