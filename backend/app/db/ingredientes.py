"""Costos y precios extra de los ingredientes del menú de La Isla, en pesos por unidad de medida.

Son valores de referencia armados para un local de pizzería del Gran Buenos Aires (2026): la muzzarella ronda los
$9.500 el kilo, el jamón cocido $12.000, la panceta $15.000, etc. No son un listado de proveedor: cada local los
ajusta desde el panel (Ingredientes) con lo que le cobra su proveedor.

- costo: lo que le cuesta al local una unidad del ingrediente (un gramo, un mililitro, una unidad).
- extra: lo que se cobra al cliente por pedirlo como adicional (una porción extra). 0 si no se vende como adicional.
- cantidad: lo que lleva habitualmente una pizza grande (o una unidad del producto), en la unidad del ingrediente.
  Las recetas se arman a partir de esta cantidad, escalada según el producto (una empanada lleva una fracción).
"""

from dataclasses import dataclass

GRAMOS = "gramos"
MILILITROS = "mililitros"
UNIDADES = "unidades"


@dataclass(frozen=True)
class DatosIngrediente:
    unidad: str
    costo: float
    extra: float
    cantidad: float


def _g(costo: float, extra: float, cantidad: float) -> DatosIngrediente:
    return DatosIngrediente(GRAMOS, costo, extra, cantidad)


def _ml(costo: float, extra: float, cantidad: float) -> DatosIngrediente:
    return DatosIngrediente(MILILITROS, costo, extra, cantidad)


def _u(costo: float, extra: float, cantidad: float = 1) -> DatosIngrediente:
    return DatosIngrediente(UNIDADES, costo, extra, cantidad)


INGREDIENTES: dict[str, DatosIngrediente] = {
    # Base
    "Masa de pizza": _g(1.8, 0, 280),
    "Salsa": _g(2.5, 0, 100),
    "Muzzarella": _g(9.5, 3500, 220),
    "Orégano": _g(14, 0, 2),
    "Aceitunas": _g(8, 1500, 25),
    "Tapa de empanada": _u(230, 0),
    "Pan de pizza": _u(1400, 0),
    "Harina de garbanzo": _g(3.8, 0, 60),
    "Papa": _g(1.7, 0, 300),
    "Aceite de girasol": _ml(2.6, 0, 30),
    "Aceite de oliva": _ml(11, 0, 10),
    # Fiambres y quesos
    "Jamón": _g(12, 3000, 70),
    "Jamón crudo": _g(30, 5500, 50),
    "Panceta": _g(15, 3500, 50),
    "Longaniza": _g(11, 3200, 90),
    "Salchicha": _g(8, 2500, 80),
    "Queso sardo": _g(15, 3200, 30),
    "Provolone": _g(12.5, 3500, 60),
    "Roquefort": _g(19, 4500, 50),
    "Cheddar": _g(12, 3200, 50),
    "Queso reggianito": _g(24, 0, 40),
    "Anchoas": _g(32, 4500, 40),
    # Verduras
    "Morrón": _g(4.5, 1500, 50),
    "Tomate": _g(3.5, 1200, 90),
    "Tomate cherry": _g(6, 1500, 80),
    "Cebolla": _g(1.3, 1000, 120),
    "Ajo": _g(7, 0, 4),
    "Albahaca": _g(22, 800, 3),
    "Rúcula": _g(6, 1500, 30),
    "Acelga": _g(3, 0, 80),
    "Choclo": _g(4.5, 1500, 80),
    "Verdeo": _g(4, 0, 20),
    "Palmitos": _g(14, 3500, 70),
    "Ananá": _g(4.5, 1500, 60),
    "Cereza": _g(14, 1500, 20),
    # Huevos y salsas
    "Huevo frito": _u(350, 1200),
    "Huevo duro": _u(350, 1200),
    "Huevo": _u(350, 1200),
    "Salsa blanca": _g(4, 0, 60),
    "Salsa golf": _g(5, 800, 20),
    "Salsa barbacoa": _g(6, 800, 25),
    "Salsa picante": _g(8, 0, 10),
    "Mostaza": _g(4, 0, 10),
    "Ketchup": _g(4, 0, 15),
    "Pimentón": _g(14, 0, 3),
    "Azúcar negra": _g(3, 0, 10),
    # Carnes
    "Carne picada": _g(9, 0, 250),
    "Carne cortada a cuchillo": _g(13, 0, 250),
    "Pollo": _g(5.8, 0, 250),
    "Vacío": _g(17, 0, 250),
    "Bondiola": _g(12, 0, 250),
    "Milanesa": _g(8.5, 0, 200),
    "Lomito": _g(19, 0, 180),
    "Churrasquito de pollo": _g(7.5, 0, 180),
}

# Ingredientes que se piden como adicional en cada tipo de producto (los que tienen precio extra).
EXTRAS_PIZZA = (
    "Muzzarella",
    "Jamón",
    "Morrón",
    "Aceitunas",
    "Huevo frito",
    "Panceta",
    "Cheddar",
    "Provolone",
    "Roquefort",
    "Cebolla",
    "Tomate",
)
EXTRAS_SANDWICH = ("Muzzarella", "Jamón", "Cheddar", "Panceta", "Huevo frito", "Tomate", "Rúcula")
EXTRAS_PAPAS = ("Cheddar", "Panceta", "Huevo frito")


def _agregar_bebidas() -> None:
    # Cada bebida es su propio ingrediente (una unidad de la botella): ver app/db/bebidas.py.
    from app.db.bebidas import BEBIDAS

    for bebida in BEBIDAS:
        INGREDIENTES[bebida.nombre] = _u(bebida.costo, 0)


_agregar_bebidas()
