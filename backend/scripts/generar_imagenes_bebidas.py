"""Genera las imágenes (PNG de 480x480) de las bebidas del seed en app/db/imagenes_bebidas.

Son ilustraciones simples de la botella con el color de cada marca, no fotos. Para usar fotos reales alcanza con
reemplazar los PNG de esa carpeta (o subirlas desde el panel, producto por producto).

    python -m scripts.generar_imagenes_bebidas
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.db.bebidas import BEBIDAS, CARPETA_IMAGENES, Bebida

LADO = 480
FONDO = "#f6f1e8"
# Alto de la botella y ancho del cuerpo según el tamaño.
FORMAS = {
    "chica": (300, 110),
    "mediana": (370, 130),
    "grande": (400, 150),
    "cerveza": (380, 100),
}


def _fuente(tamano: int) -> ImageFont.ImageFont:
    for ruta in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _oscurecer(color: str, factor: float = 0.75) -> str:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def dibujar(bebida: Bebida) -> Image.Image:
    imagen = Image.new("RGB", (LADO, LADO), FONDO)
    d = ImageDraw.Draw(imagen)
    alto, ancho = FORMAS[bebida.tamano]
    centro = LADO // 2
    base = LADO - 40
    tope = base - alto
    # Sombra
    d.ellipse((centro - ancho // 2 - 10, base - 8, centro + ancho // 2 + 10, base + 14), fill="#ddd5c6")

    cuello = ancho // 3 if bebida.tamano != "cerveza" else ancho // 4
    alto_cuello = alto // 4 if bebida.tamano != "cerveza" else alto // 3
    # Cuerpo y cuello (botella)
    d.rounded_rectangle(
        (centro - ancho // 2, tope + alto_cuello, centro + ancho // 2, base),
        radius=28,
        fill=bebida.liquido,
        outline=_oscurecer(bebida.liquido),
        width=3,
    )
    d.rounded_rectangle(
        (centro - cuello // 2, tope + 14, centro + cuello // 2, tope + alto_cuello + 30),
        radius=10,
        fill=bebida.liquido,
        outline=_oscurecer(bebida.liquido),
        width=3,
    )
    # Tapa
    tapa = bebida.etiqueta if bebida.tamano != "cerveza" else "#d9b84a"
    d.rounded_rectangle((centro - cuello // 2 - 2, tope, centro + cuello // 2 + 2, tope + 24), radius=6, fill=tapa)
    # Brillo
    d.rounded_rectangle(
        (centro - ancho // 2 + 10, tope + alto_cuello + 12, centro - ancho // 2 + 20, base - 18),
        radius=5,
        fill=_aclarar(bebida.liquido),
    )
    # Etiqueta
    y0 = tope + alto_cuello + (alto - alto_cuello) // 4
    y1 = base - (alto - alto_cuello) // 5
    d.rectangle((centro - ancho // 2, y0, centro + ancho // 2, y1), fill=bebida.etiqueta)

    # Texto de la marca centrado en la etiqueta
    texto = bebida.marca
    tamano_fuente = 26
    fuente = _fuente(tamano_fuente)
    while d.textlength(texto, font=fuente) > ancho - 14 and tamano_fuente > 10:
        tamano_fuente -= 2
        fuente = _fuente(tamano_fuente)
    ancho_texto = d.textlength(texto, font=fuente)
    d.text((centro - ancho_texto / 2, (y0 + y1) / 2 - tamano_fuente / 2), texto, fill="#ffffff", font=fuente)
    return imagen


def _aclarar(color: str) -> str:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return f"#{min(255, r + 70):02x}{min(255, g + 70):02x}{min(255, b + 70):02x}"


def main() -> None:
    CARPETA_IMAGENES.mkdir(parents=True, exist_ok=True)
    for bebida in BEBIDAS:
        destino: Path = bebida.archivo_imagen
        dibujar(bebida).save(destino, optimize=True)
        print(destino.name)


if __name__ == "__main__":
    main()
