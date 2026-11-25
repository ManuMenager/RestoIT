"""Bebidas del local con su precio de venta, su costo y la imagen que se muestra en el menú.

Las imágenes están en app/db/imagenes_bebidas (se generan con scripts/generar_imagenes_bebidas.py) y se cargan a la
base junto con el producto. Cada bebida es también un ingrediente de su propia receta (una unidad), así los reportes
de consumo y de costos incluyen lo que se vende por botella.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CARPETA_IMAGENES = Path(__file__).parent / "imagenes_bebidas"


@dataclass(frozen=True)
class Bebida:
    nombre: str
    descripcion: str
    precio: float
    # Lo que le cuesta al local la botella (precio de mayorista de referencia).
    costo: float
    # Colores de la imagen: líquido, etiqueta y tapa; tamaño de la botella: "chica", "mediana", "grande" o "cerveza".
    liquido: str
    etiqueta: str
    tamano: str
    # Texto corto para la etiqueta de la imagen.
    marca: str

    @property
    def archivo_imagen(self) -> Path:
        return CARPETA_IMAGENES / f"{_slug(self.nombre)}.png"


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


_COLA = "#2b1208"
_SPRITE = "#eaf6e2"
_FANTA = "#f4891c"
_AGUA = "#e1f2fb"
_AMBAR = "#b8700f"

BEBIDAS = [
    Bebida("Coca-Cola 500ml", "Coca-Cola, botella de 500ml.", 3500, 1500, _COLA, "#d81f26", "chica", "Coca-Cola"),
    Bebida("Coca-Cola 1.5L", "Coca-Cola, botella de 1,5 litros.", 6500, 3300, _COLA, "#d81f26", "mediana", "Coca-Cola"),
    Bebida(
        "Coca-Cola 2.25L", "Coca-Cola, botella de 2,25 litros.", 8500, 4300, _COLA, "#d81f26", "grande", "Coca-Cola"
    ),
    Bebida(
        "Coca-Cola Zero 500ml",
        "Coca-Cola Zero azúcar, botella de 500ml.",
        3500,
        1500,
        _COLA,
        "#1a1a1a",
        "chica",
        "Coca-Cola Zero",
    ),
    Bebida(
        "Coca-Cola Zero 1.5L",
        "Coca-Cola Zero azúcar, botella de 1,5 litros.",
        6500,
        3300,
        _COLA,
        "#1a1a1a",
        "mediana",
        "Coca-Cola Zero",
    ),
    Bebida("Sprite 500ml", "Sprite lima limón, botella de 500ml.", 3500, 1500, _SPRITE, "#1c9b3d", "chica", "Sprite"),
    Bebida(
        "Sprite 1.5L", "Sprite lima limón, botella de 1,5 litros.", 6300, 3200, _SPRITE, "#1c9b3d", "mediana", "Sprite"
    ),
    Bebida("Fanta 500ml", "Fanta naranja, botella de 500ml.", 3500, 1500, _FANTA, "#f26a10", "chica", "Fanta"),
    Bebida("Fanta 1.5L", "Fanta naranja, botella de 1,5 litros.", 6300, 3200, _FANTA, "#f26a10", "mediana", "Fanta"),
    Bebida(
        "Agua Mineral 500ml", "Agua mineral sin gas, botella de 500ml.", 2500, 900, _AGUA, "#2f8fd1", "chica", "Agua"
    ),
    Bebida(
        "Agua Mineral con Gas 500ml",
        "Agua mineral con gas, botella de 500ml.",
        2500,
        900,
        _AGUA,
        "#13a4a0",
        "chica",
        "Agua con gas",
    ),
    Bebida(
        "Agua Mineral 1.5L",
        "Agua mineral sin gas, botella de 1,5 litros.",
        3800,
        1400,
        _AGUA,
        "#2f8fd1",
        "mediana",
        "Agua",
    ),
    Bebida(
        "Cerveza Quilmes 1L",
        "Cerveza Quilmes rubia, botella retornable de 1 litro.",
        6500,
        3300,
        _AMBAR,
        "#1d5fa8",
        "cerveza",
        "Quilmes",
    ),
    Bebida(
        "Cerveza Brahma 1L",
        "Cerveza Brahma rubia, botella de 1 litro.",
        6000,
        3000,
        _AMBAR,
        "#c8102e",
        "cerveza",
        "Brahma",
    ),
    Bebida(
        "Cerveza Stella Artois 1L",
        "Cerveza Stella Artois premium, botella de 1 litro.",
        8500,
        4500,
        _AMBAR,
        "#b89b2e",
        "cerveza",
        "Stella Artois",
    ),
    Bebida(
        "Cerveza Andes Origen 1L",
        "Cerveza Andes Origen rubia, botella de 1 litro.",
        7500,
        3900,
        _AMBAR,
        "#8c1d1d",
        "cerveza",
        "Andes",
    ),
    Bebida(
        "Cerveza Patagonia Amber Lager 730ml",
        "Cerveza Patagonia Amber Lager, botella de 730ml.",
        9000,
        5000,
        _AMBAR,
        "#2f6f3e",
        "cerveza",
        "Patagonia",
    ),
]

NOMBRES_DE_BEBIDAS = {bebida.nombre for bebida in BEBIDAS}
