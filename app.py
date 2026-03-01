import io
import os
import asyncio
import httpx
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor

# ================= ADJUSTMENT SETTINGS =================
AVATAR_ZOOM = 1.26
AVATAR_SHIFT_Y = 0
AVATAR_SHIFT_X = 0

BANNER_START_X = 0.25
BANNER_START_Y = 0.29
BANNER_END_X = 0.81
BANNER_END_Y = 0.65
# ======================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()
    process_pool.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INFO_API_URL = "https://fffinfo.tsunstudio.pw/get"
BASE64 = "aHR0cHM6Ly9jZG4uanNkZWxpdnIubmV0L2doL1NoYWhHQ3JlYXRvci9pY29uQG1haW4vUE5H"
info_URL = base64.b64decode(BASE64).decode("utf-8")

FONT_FILE = "arial_unicode_bold.otf"
FONT_CHEROKEE = "NotoSansCherokee.ttf"

client = httpx.AsyncClient(
    headers={"User-Agent": "Mozilla/5.0"},
    timeout=10.0,
    follow_redirects=True
)

process_pool = ThreadPoolExecutor(max_workers=4)

# ================= HELPERS =================
def load_unicode_font(size, font_file=FONT_FILE):
    try:
        font_path = os.path.join(os.path.dirname(__file__), font_file)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except:
        pass
    return ImageFont.load_default()

async def fetch_image_bytes(item_id):
    if not item_id or str(item_id) == "0":
        return None
    try:
        resp = await client.get(f"{info_URL}/{item_id}.png")
        if resp.status_code == 200:
            return resp.content
    except:
        pass
    return None

def bytes_to_image(img_bytes):
    if img_bytes:
        return Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    return Image.new("RGBA", (100, 100), (0, 0, 0, 0))

# ================= IMAGE PROCESS =================
def process_banner_image(data, avatar_bytes, banner_bytes, pin_bytes):
    avatar_img = bytes_to_image(avatar_bytes)
    banner_img = bytes_to_image(banner_bytes)
    pin_img = bytes_to_image(pin_bytes)

    level = str(data.get("AccountLevel") or "0")
    name = str(data.get("AccountName") or "Unknown")
    guild = str(data.get("GuildName") or "")

    TARGET_HEIGHT = 400

    zoom_size = int(TARGET_HEIGHT * AVATAR_ZOOM)
    avatar_img = avatar_img.resize((zoom_size, zoom_size), Image.LANCZOS)

    c = zoom_size // 2
    h = TARGET_HEIGHT // 2
    avatar_img = avatar_img.crop((
        c - h - AVATAR_SHIFT_X,
        c - h - AVATAR_SHIFT_Y,
        c + h - AVATAR_SHIFT_X,
        c + h - AVATAR_SHIFT_Y
    ))

    banner_img = banner_img.rotate(3, expand=True)
    bw, bh = banner_img.size
    banner_img = banner_img.crop((
        bw * BANNER_START_X,
        bh * BANNER_START_Y,
        bw * BANNER_END_X,
        bh * BANNER_END_Y
    ))

    bw, bh = banner_img.size
    banner_img = banner_img.resize(
        (int(TARGET_HEIGHT * (bw / bh) * 2), TARGET_HEIGHT),
        Image.LANCZOS
    )

    final = Image.new("RGBA", (avatar_img.width + banner_img.width, TARGET_HEIGHT))
    final.paste(avatar_img, (0, 0))
    final.paste(banner_img, (avatar_img.width, 0))

    draw = ImageDraw.Draw(final)

    font_big = load_unicode_font(125)
    font_big_c = load_unicode_font(125, FONT_CHEROKEE)
    font_small = load_unicode_font(95)
    font_small_c = load_unicode_font(95, FONT_CHEROKEE)
    font_lvl = load_unicode_font(50)

    def is_cherokee(c):
        return 0x13A0 <= ord(c) <= 0x13FF or 0xAB70 <= ord(c) <= 0xABBF

    def draw_text(x, y, text, f_main, f_alt, stroke):
        text = text or ""
        cx = x
        for ch in text:
            f = f_alt if is_cherokee(ch) else f_main
            for dx in range(-stroke, stroke + 1):
                for dy in range(-stroke, stroke + 1):
                    draw.text((cx + dx, y + dy), ch, font=f, fill="black")
            draw.text((cx, y), ch, font=f, fill="white")
            cx += f.getlength(ch)

    draw_text(avatar_img.width + 65, 40, name, font_big, font_big_c, 4)
    draw_text(avatar_img.width + 65, 220, guild, font_small, font_small_c, 3)

    if pin_img.size != (100, 100):
        pin_img = pin_img.resize((130, 130))
        final.paste(pin_img, (0, TARGET_HEIGHT - 130), pin_img)

    lvl = f"Lvl.{level}"
    w, h = draw.textbbox((0, 0), lvl, font=font_lvl)[2:]
    draw.rectangle(
        [final.width - w - 60, TARGET_HEIGHT - h - 50, final.width, TARGET_HEIGHT],
        fill="black"
    )
    draw.text(
        (final.width - w - 30, TARGET_HEIGHT - h - 40),
        lvl,
        font=font_lvl,
        fill="white"
    )

    out = io.BytesIO()
    final.save(out, "PNG")
    out.seek(0)
    return out

# ================= ROUTES =================
@app.get("/")
async def home():
    return {"status": "Banner API Running", "endpoint": "/rizer?uid=UID"}

@app.get("/rizer")
async def get_banner(uid: str):
    resp = await client.get(f"{INFO_API_URL}?uid={uid}")
    if resp.status_code != 200:
        raise HTTPException(502, "Info API Error")

    data = resp.json()
    acc = data.get("AccountInfo") or {}
    eq = data.get("EquippedItemsInfo") or {}
    gl = data.get("GuildInfo") or {}

    if not acc:
        raise HTTPException(404, "Account not found")

    avatar, banner, pin = await asyncio.gather(
        fetch_image_bytes(eq.get("EquippedAvatarId")),
        fetch_image_bytes(eq.get("EquippedBannerId")),
        fetch_image_bytes(eq.get("pinId")),
    )

    img = await asyncio.get_event_loop().run_in_executor(
        process_pool,
        process_banner_image,
        {
            "AccountLevel": acc.get("AccountLevel"),
            "AccountName": acc.get("AccountName"),
            "GuildName": gl.get("GuildName"),
        },
        avatar, banner, pin
    )

    return Response(img.getvalue(), media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)