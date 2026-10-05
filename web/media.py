"""Upload de imagens (avatar de jogador e logo de time).

A imagem é aberta com Pillow, validada, recortada/ajustada para quadrado, reduzida e regravada em WebP.
Regravar descarta metadados (EXIF/GPS) e qualquer conteúdo que não seja imagem.
"""
import io, re
from flask import Blueprint, abort, make_response
from PIL import Image, ImageOps, UnidentifiedImageError
from web.extensions import db
from web.models import MediaFile

bp = Blueprint('media', __name__)

MAX_BYTES = 5 * 1024 * 1024
SIZE = 256
ALLOWED = {'JPEG', 'PNG', 'WEBP', 'GIF'}
URL_RE = re.compile(r'^/media/(\d+)\.webp$')
Image.MAX_IMAGE_PIXELS = 40_000_000  # evita "bombas" de descompressão


def save_image(file, kind, owner_id=None):
    """Recebe um FileStorage do formulário e devolve a URL interna (/media/<id>.webp)."""
    raw = file.read(MAX_BYTES + 1)
    if not raw: raise ValueError('Escolha uma imagem.')
    if len(raw) > MAX_BYTES: raise ValueError('A imagem pode ter no máximo 5 MB.')
    try:
        img = Image.open(io.BytesIO(raw))
        if img.format not in ALLOWED: raise ValueError('Formato não suportado. Envie JPG, PNG, WEBP ou GIF.')
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('Esse arquivo não é uma imagem válida.')
    img = ImageOps.exif_transpose(img)
    if kind == 'logo':
        # Logo: mantém a arte inteira centralizada em fundo transparente.
        img = img.convert('RGBA'); img.thumbnail((SIZE, SIZE), Image.LANCZOS)
        canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2), img); img = canvas
    else:
        # Avatar: recorta o centro em quadrado.
        img = ImageOps.fit(img.convert('RGB'), (SIZE, SIZE), Image.LANCZOS)
    out = io.BytesIO(); img.save(out, 'WEBP', quality=85, method=6)
    row = MediaFile(kind=kind, data=out.getvalue(), size=out.tell(), owner_id=owner_id)
    db.session.add(row); db.session.flush()
    return f'/media/{row.id}.webp'


def delete_if_local(url):
    """Apaga a imagem antiga quando ela foi enviada para o site (links externos antigos são ignorados)."""
    m = URL_RE.match(url or '')
    if m: MediaFile.query.filter_by(id=int(m.group(1))).delete()


@bp.get('/media/<int:mid>.webp')
def serve(mid):
    row = db.session.get(MediaFile, mid) or abort(404)
    resp = make_response(row.data)
    resp.headers['Content-Type'] = row.content_type
    resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'  # cada envio gera um id novo
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
