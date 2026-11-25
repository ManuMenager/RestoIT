"""Carga el menú de La Isla (pizzas y empanadas) tal como figura en sus cartas, con los datos del local y sus horarios.

    python -m app.db.menu_la_isla

Se puede correr más de una vez: actualiza lo que ya está (por nombre) y no duplica nada. Saca del menú los productos
de ejemplo que carga el seed (los que figuran en pedidos se archivan y el resto se borran), y también sus categorías e
ingredientes si quedaron sin uso. Lo que se haya cargado a mano desde el panel no se toca.

Las cartas no dicen cuánto de cada ingrediente lleva cada producto: las recetas se cargan con una porción de cada
uno (dos de muzzarella en la Muzzarella Doble), para que se puedan pedir sin un ingrediente y contar el consumo.
Las cantidades y costos reales se ajustan después desde el panel.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import time

from sqlalchemy.orm import Session

from app.core.errors import DomainError

# Registra todos los modelos: al correr el script solo, sin esto SQLAlchemy no encuentra las clases
# que las relaciones nombran como texto (por ejemplo DeliveryDriver desde Order).
from app.db import base  # noqa: F401
from app.db.bebidas import BEBIDAS
from app.db.ingredientes import (
    EXTRAS_PAPAS,
    EXTRAS_PIZZA,
    EXTRAS_SANDWICH,
    INGREDIENTES,
    UNIDADES,
)
from app.db.seed import CATEGORIAS_DE_EJEMPLO, INGREDIENTES_DE_EJEMPLO, PRODUCTOS_DE_EJEMPLO, cargar_bebida
from app.db.session import SessionLocal, transaction
from app.models.menu import Category, Ingredient, Product
from app.models.promotion import Promotion
from app.models.store_config import StoreConfig
from app.services import catalog_service
from app.services.business_hours_service import Franja, guardar_franjas

logger = logging.getLogger(__name__)

STORE_NAME = "La Isla"
STORE_ADDRESS = "O'Higgins 999 esq. Tucumán, Quilmes Oeste"
STORE_PHONE = "4976-0078 / 4040-9695 / WhatsApp 11-3016-5712"

GRANDE_CHICA = ("Grande", "Chica")
CARNE_POLLO = ("Carne", "Pollo")


@dataclass(frozen=True)
class Producto:
    nombre: str
    descripcion: str
    # Un precio, o uno por variante en el orden de la categoría (ej. Grande y Chica).
    precios: tuple[float, ...]
    # Receta: (ingrediente del local, cantidad en su unidad de medida). Los ingredientes de la carta son los de la
    # descripción; el resto (masa, tapa, aceite) se agrega para que el costo del producto sea completo.
    receta: tuple[tuple[str, float], ...] = ()
    restricciones: tuple[str, ...] = ()


@dataclass(frozen=True)
class Seccion:
    categoria: str
    sector: str
    variantes: tuple[str, ...]
    productos: list[Producto] = field(default_factory=list)
    # Ingredientes que se pueden pedir como adicional en los productos de la sección.
    extras: tuple[str, ...] = ()


def _cantidad(nombre: str, escala: float) -> float:
    """Cantidad habitual del ingrediente en el producto; lo que se cuenta por unidad (tapas, huevos) no se escala."""
    datos = INGREDIENTES[nombre]
    return round(datos.cantidad * (1 if datos.unidad == UNIDADES else escala), 1)


def _receta(*ingredientes: str, escala: float = 1.0) -> tuple[tuple[str, float], ...]:
    return tuple((nombre, _cantidad(nombre, escala)) for nombre in ingredientes)


def _doble(receta: tuple[tuple[str, float], ...], ingrediente: str) -> tuple[tuple[str, float], ...]:
    return tuple((nombre, cantidad * 2 if nombre == ingrediente else cantidad) for nombre, cantidad in receta)


def _descripcion(ingredientes: tuple[str, ...]) -> str:
    nombres = [ingredientes[0], *(n.lower() for n in ingredientes[1:])]
    texto = nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"
    return f"{texto}."


def _con_ingredientes(
    nombre: str,
    precios: tuple[float, ...],
    *ingredientes: str,
    agregados: tuple[str, ...] = (),
    escala: float = 1.0,
    **extra,
) -> Producto:
    """Producto cuya descripción son sus ingredientes; `agregados` suma a la receta lo que la carta no nombra."""
    return Producto(
        nombre, _descripcion(ingredientes), precios, _receta(*agregados, *ingredientes, escala=escala), **extra
    )


def _pizza(nombre: str, precios: tuple[float, ...], *ingredientes: str, **extra) -> Producto:
    return _con_ingredientes(nombre, precios, *ingredientes, agregados=("Masa de pizza",), **extra)


def _empanada(nombre: str, precios: tuple[float, ...], *ingredientes: str, **extra) -> Producto:
    return _con_ingredientes(nombre, precios, *ingredientes, agregados=("Tapa de empanada",), escala=0.12, **extra)


_BASE = ("Salsa", "Muzzarella")
_FINAL = ("Orégano", "Aceitunas")

PIZZAS = Seccion(
    "Pizzas",
    "pizzeria",
    GRANDE_CHICA,
    [
        _pizza("Muzzarella", (16000, 14000), *_BASE, *_FINAL),
        Producto(
            "Muzzarella Doble",
            "Salsa, doble muzzarella, orégano y aceitunas.",
            (19000, 17000),
            _doble(_receta("Masa de pizza", *_BASE, *_FINAL), "Muzzarella"),
        ),
        _pizza("Muzzarella con Jamón", (19000, 17000), *_BASE, "Jamón", *_FINAL),
        _pizza("Muzzarella con Morrón", (19000, 17000), *_BASE, "Morrón", *_FINAL),
        _pizza("Especial", (20000, 18000), *_BASE, "Jamón", "Morrón", *_FINAL),
        _pizza("Napolitana", (19000, 17000), *_BASE, "Tomate", "Queso sardo", "Ajo", *_FINAL),
        _pizza("Napolitana con Jamón", (20000, 18000), *_BASE, "Jamón", "Tomate", "Queso sardo", "Ajo", *_FINAL),
        _pizza("Calabresa", (19500, 17500), *_BASE, "Longaniza", *_FINAL),
        _pizza("Fugazza", (16000, 14000), "Cebolla", *_FINAL),
        _pizza("Fugazza con Muzza", (19000, 17000), "Cebolla", "Muzzarella", *_FINAL),
        _pizza("Fugazza con Muzza y Jamón", (20000, 18000), "Cebolla", "Muzzarella", "Jamón", *_FINAL),
        _pizza("Americana", (21000, 19000), *_BASE, "Jamón", "Huevo frito", *_FINAL),
        _pizza("Cuatro Quesos", (21000, 19000), *_BASE, "Provolone", "Queso sardo", "Roquefort", *_FINAL),
        _pizza("Provolone", (20000, 18000), *_BASE, "Provolone", "Morrón", *_FINAL),
        _pizza("Roquefort", (20000, 18000), *_BASE, "Roquefort", "Morrón", *_FINAL),
        _pizza("Capresse", (20000, 18000), *_BASE, "Tomate", "Albahaca", *_FINAL, restricciones=("vegetariano",)),
        _pizza("Marinera", (20000, 18000), *_BASE, "Huevo duro", "Morrón", *_FINAL),
        _pizza("Romana", (21000, 19000), *_BASE, "Huevo duro", "Jamón", *_FINAL),
        _pizza("Alemana", (20000, 18000), *_BASE, "Salchicha", "Mostaza", *_FINAL),
        _pizza("Rúcula con Jamón Crudo", (21000, 19000), *_BASE, "Jamón crudo", "Rúcula", *_FINAL),
        _pizza(
            "Especial La Isla",
            (22000, 20000),
            "Cebolla",
            "Muzzarella",
            "Huevo duro",
            "Panceta",
            "Cheddar",
            *_FINAL,
        ),
        _pizza("Palmitos", (22000, 20000), *_BASE, "Palmitos", "Huevo duro", "Morrón", "Salsa golf", *_FINAL),
        _pizza(
            "Verdura",
            (20000, 18000),
            *_BASE,
            "Acelga",
            "Salsa blanca",
            "Cebolla",
            "Queso sardo",
            "Morrón",
            *_FINAL,
            restricciones=("vegetariano",),
        ),
        _pizza("Sorrentina", (21000, 19000), *_BASE, "Jamón", "Provolone", *_FINAL),
        _pizza(
            "Humita",
            (20000, 18000),
            *_BASE,
            "Choclo",
            "Salsa blanca",
            "Morrón",
            *_FINAL,
            restricciones=("vegetariano",),
        ),
        _pizza("Panceta Provolone", (22000, 20000), *_BASE, "Panceta", "Provolone", *_FINAL),
        _pizza("Brasilera", (20000, 18000), *_BASE, "Jamón", "Ananá", "Cereza", "Azúcar negra"),
        _pizza("Anchoas", (18000, 16000), "Salsa", "Anchoas", *_FINAL),
        _pizza("Anchoas con Muzzarella", (19000, 17000), *_BASE, "Anchoas", *_FINAL),
        _pizza("Cheddar y Bacon", (22000, 20000), *_BASE, "Panceta", "Cheddar", "Salsa barbacoa", *_FINAL),
    ],
    extras=EXTRAS_PIZZA,
)

_R_FUGAZZETA = ("Masa de pizza", "Cebolla", "Muzzarella")

PIZZAS_RELLENAS = Seccion(
    "Pizzas Rellenas",
    "pizzeria",
    (),
    [
        Producto(
            "Porción de Fugazzeta (JyQ)",
            "Porción de fugazzeta rellena de jamón y queso.",
            (3500,),
            _receta(*_R_FUGAZZETA, "Jamón", escala=0.15),
        ),
        Producto(
            "Fugazzeta con Muzzarella",
            "Fugazzeta rellena de muzzarella.",
            (24000,),
            _doble(_receta(*_R_FUGAZZETA, escala=1.4), "Muzzarella"),
        ),
        Producto(
            "Fugazzeta con Muzza y Jamón",
            "Fugazzeta rellena de muzzarella y jamón.",
            (27000,),
            _doble(_receta(*_R_FUGAZZETA, "Jamón", escala=1.4), "Muzzarella"),
        ),
        Producto(
            "Fugazzeta con Jamón y Tomate",
            "Fugazzeta rellena de jamón y tomate.",
            (28000,),
            _receta(*_R_FUGAZZETA, "Jamón", "Tomate", escala=1.4),
        ),
        Producto(
            "Calzone Napolitano",
            "Calzone napolitano.",
            (23000,),
            _receta("Masa de pizza", "Salsa", "Muzzarella", "Jamón", "Tomate", "Orégano", escala=1.2),
        ),
        Producto(
            "Calzone Germano",
            "Calzone germano.",
            (22000,),
            _receta("Masa de pizza", "Salsa", "Muzzarella", "Salchicha", "Mostaza", escala=1.2),
        ),
        Producto(
            "Calzone Calabrés",
            "Calzone calabrés.",
            (22000,),
            _receta("Masa de pizza", "Salsa", "Muzzarella", "Longaniza", "Morrón", escala=1.2),
        ),
    ],
    extras=EXTRAS_PIZZA,
)

_PIZZANEZA = ("Milanesa", "Papa", "Aceite de girasol")

PIZZANEZAS = Seccion(
    "Pizzanezas",
    "pizzeria",
    CARNE_POLLO,
    [
        Producto(
            "Pizzaneza Napolitana",
            "Milanesa de carne o pollo a la napolitana, con lluvia de papas fritas.",
            (38000, 36000),
            _receta(*_PIZZANEZA, "Salsa", "Muzzarella", "Tomate", "Ajo"),
        ),
        Producto(
            "Pizzaneza 4 Quesos",
            "Milanesa de carne o pollo cuatro quesos, con lluvia de papas fritas.",
            (38000, 36000),
            _receta(*_PIZZANEZA, "Salsa", "Muzzarella", "Provolone", "Queso sardo", "Roquefort"),
        ),
        Producto(
            "Pizzaneza La Isla",
            "Milanesa de carne o pollo especial La Isla, con lluvia de papas fritas.",
            (44000, 41000),
            _receta(*_PIZZANEZA, "Salsa", "Muzzarella", "Jamón", "Huevo frito", "Panceta", "Cheddar"),
        ),
        Producto(
            "Pizzaneza Fugazza",
            "Milanesa de carne o pollo a la fugazza, con lluvia de papas fritas.",
            (36000, 34000),
            _receta(*_PIZZANEZA, "Cebolla", "Muzzarella"),
        ),
    ],
    extras=EXTRAS_SANDWICH,
)

FAINA = Seccion(
    "Fainá",
    "pizzeria",
    (),
    [
        Producto(
            "Fainá Tradicional",
            "Porción de fainá tradicional.",
            (1500,),
            _receta("Harina de garbanzo", "Aceite de girasol"),
            ("vegetariano",),
        ),
        Producto(
            "Fainá al Verdeo",
            "Porción de fainá al verdeo.",
            (2000,),
            _receta("Harina de garbanzo", "Aceite de girasol", "Verdeo"),
            ("vegetariano",),
        ),
        Producto(
            "Fainá Rellena",
            "Porción de fainá rellena.",
            (3000,),
            _receta("Harina de garbanzo", "Aceite de girasol", "Muzzarella", "Jamón", escala=0.5),
        ),
    ],
)

_EMPANADA = (2500,)

EMPANADAS = Seccion(
    "Empanadas",
    "cocina",
    (),
    [
        _empanada("Empanada Carne Suave", _EMPANADA, "Carne picada", "Cebolla", "Huevo", "Morrón", "Verdeo"),
        _empanada(
            "Empanada Carne Picante", _EMPANADA, "Carne picada", "Cebolla", "Verdeo", "Pimentón", "Salsa picante"
        ),
        _empanada(
            "Empanada Carne Cuchillo", _EMPANADA, "Carne cortada a cuchillo", "Morrón", "Verdeo", "Cebolla", "Huevo"
        ),
        _empanada("Empanada Jamón y Queso", _EMPANADA, "Jamón", "Muzzarella"),
        _empanada(
            "Empanada Cebolla y Queso", _EMPANADA, "Cebolla", "Orégano", "Muzzarella", restricciones=("vegetariano",)
        ),
        _empanada("Empanada Pollo al Roquefort", _EMPANADA, "Pollo", "Roquefort", "Jamón", "Muzzarella"),
        _empanada("Empanada Pollo al Verdeo", _EMPANADA, "Pollo", "Verdeo", "Salsa blanca"),
        _empanada(
            "Empanada Capresse",
            _EMPANADA,
            "Tomate cherry",
            "Albahaca",
            "Muzzarella",
            "Aceite de oliva",
            restricciones=("vegetariano",),
        ),
        _empanada("Empanada Alemana", _EMPANADA, "Salchicha", "Mostaza", "Muzzarella"),
        _empanada("Empanada Calabresa", _EMPANADA, "Muzzarella", "Longaniza"),
        _empanada(
            "Empanada Humita",
            _EMPANADA,
            "Choclo",
            "Cebolla",
            "Salsa blanca",
            "Queso reggianito",
            restricciones=("vegetariano",),
        ),
        _empanada("Empanada Pollo", _EMPANADA, "Pollo", "Cebolla", "Huevo", "Morrón", "Verdeo"),
        _empanada(
            "Empanada Verdura",
            _EMPANADA,
            "Acelga",
            "Cebolla",
            "Salsa blanca",
            "Queso reggianito",
            restricciones=("vegetariano",),
        ),
        _empanada("Empanada Roquefort con Jamón", _EMPANADA, "Muzzarella", "Jamón", "Roquefort"),
        _empanada("Empanada Jamón y Ananá", _EMPANADA, "Jamón", "Muzzarella", "Ananá"),
        _empanada("Empanada Salchicha y Cheddar", _EMPANADA, "Salchicha", "Cheddar"),
        Producto(
            "Empanada Cheeseburguer",
            "Empanada de cheeseburguer.",
            _EMPANADA,
            _receta("Tapa de empanada", "Carne picada", "Cheddar", "Cebolla", "Ketchup", escala=0.12),
        ),
        Producto(
            "Empanada Vacío",
            "Empanada de vacío.",
            _EMPANADA,
            _receta("Tapa de empanada", "Vacío", "Cebolla", "Morrón", escala=0.12),
        ),
        Producto(
            "Empanada Bondiola",
            "Empanada de bondiola.",
            _EMPANADA,
            _receta("Tapa de empanada", "Bondiola", "Cebolla", "Salsa barbacoa", escala=0.12),
        ),
    ],
)

SANDWICHES = Seccion(
    "Sándwiches",
    "cocina",
    CARNE_POLLO,
    [
        Producto(
            "Milanesa Individual",
            "Sándwich individual de milanesa de carne o pollo, con pan de pizza.",
            (8000, 7000),
            _receta("Pan de pizza", "Milanesa", escala=0.5),
        ),
        Producto(
            "Milanesa Simple",
            "Milanesa de carne o pollo, con pan de pizza. Para compartir.",
            (16000, 14000),
            _receta("Pan de pizza", "Milanesa", escala=0.8),
        ),
        Producto(
            "Milanesa Completa",
            "Milanesa de carne o pollo, tomate, cheddar, jamón y huevo rallado, con pan de pizza. Para compartir.",
            (19000, 17000),
            _receta("Pan de pizza", "Milanesa", "Tomate", "Cheddar", "Jamón", "Huevo duro", escala=0.8),
        ),
    ],
    extras=EXTRAS_SANDWICH,
)

SANDWICHES_SIN_VARIANTES = Seccion(
    "Sándwiches",
    "cocina",
    (),
    [
        Producto(
            "Lomo y Muzzarella",
            "Lomito y muzzarella, con pan de pizza. Para compartir.",
            (21000,),
            _receta("Pan de pizza", "Lomito", "Muzzarella", escala=0.8),
        ),
        Producto(
            "Pollo y Muzzarella",
            "Churrasquito de pollo y muzzarella, con pan de pizza. Para compartir.",
            (17000,),
            _receta("Pan de pizza", "Churrasquito de pollo", "Muzzarella", escala=0.8),
        ),
        Producto(
            "Especial de Lomo",
            "Lomito, cheddar, cebolla, muzzarella, huevo y panceta, con pan de pizza. Para compartir.",
            (23000,),
            _receta("Pan de pizza", "Lomito", "Cheddar", "Cebolla", "Muzzarella", "Huevo", "Panceta", escala=0.8),
        ),
        Producto(
            "Especial de Pollo",
            "Churrasquito de pollo, muzzarella, rúcula, tomate y jamón crudo, con pan de pizza. Para compartir.",
            (19000,),
            _receta(
                "Pan de pizza", "Churrasquito de pollo", "Muzzarella", "Rúcula", "Tomate", "Jamón crudo", escala=0.8
            ),
        ),
        Producto(
            "Veggie Capresse",
            "Muzzarella, tomate y albahaca, con pan de pizza. Para compartir.",
            (11000,),
            _receta("Pan de pizza", "Muzzarella", "Tomate", "Albahaca", escala=0.8),
            ("vegetariano",),
        ),
        Producto(
            "Veggie Especial Rúcula",
            "Muzzarella, tomate, rúcula, ajo y queso sardo, con pan de pizza. Para compartir.",
            (11000,),
            _receta("Pan de pizza", "Muzzarella", "Tomate", "Rúcula", "Ajo", "Queso sardo", escala=0.8),
            ("vegetariano",),
        ),
    ],
    extras=EXTRAS_SANDWICH,
)

PAPAS = Seccion(
    "Papas Fritas",
    "cocina",
    (),
    [
        Producto(
            "Porción de Fritas",
            "Porción de papas fritas.",
            (7000,),
            _receta("Papa", "Aceite de girasol"),
            ("vegetariano",),
        ),
        Producto(
            "Porción de Fritas con Panceta y Cheddar",
            "Papas fritas con panceta y cheddar.",
            (10000,),
            _receta("Papa", "Aceite de girasol", "Panceta", "Cheddar"),
        ),
    ],
    extras=EXTRAS_PAPAS,
)

BEBIDAS_DE_LA_CARTA = Seccion("Bebidas", "barra", ())

SECCIONES = [
    PIZZAS,
    PIZZAS_RELLENAS,
    PIZZANEZAS,
    FAINA,
    EMPANADAS,
    SANDWICHES,
    SANDWICHES_SIN_VARIANTES,
    PAPAS,
    BEBIDAS_DE_LA_CARTA,
]


@dataclass(frozen=True)
class Promo:
    nombre: str
    descripcion: str
    precio: float
    # (producto, cantidad, variante)
    productos: tuple[tuple[str, int, str | None], ...]


# Solo las promos de la carta que se arman con productos fijos del menú. Las que llevan bebidas (no están en la
# carta) o empanadas a elección no se pueden cargar todavía: una promo incluye productos puntuales.
PROMOS = [
    Promo("3 Muzzarellas", "Tres pizzas muzzarella grandes.", 42000, (("Muzzarella", 3, "Grande"),)),
    Promo(
        "Muzzarella + Especial + Napolitana",
        "Una muzzarella, una especial y una napolitana, grandes.",
        49000,
        (("Muzzarella", 1, "Grande"), ("Especial", 1, "Grande"), ("Napolitana", 1, "Grande")),
    ),
    Promo(
        "Muzzarella + Especial",
        "Una muzzarella y una especial, grandes.",
        34000,
        (("Muzzarella", 1, "Grande"), ("Especial", 1, "Grande")),
    ),
    Promo(
        "Sándwich de Milanesa de Pollo con Jamón y Queso",
        "Sándwich de milanesa de pollo con jamón y queso.",
        15000,
        (("Milanesa Simple", 1, "Pollo"),),
    ),
]

# Lunes a sábado de 11 a 15 y de 19 a 00; domingos de 19 a 00 (0 = lunes ... 6 = domingo).
HORARIOS = [
    *(Franja(dia=dia, apertura=time(11), cierre=time(15)) for dia in range(6)),
    *(Franja(dia=dia, apertura=time(19), cierre=time(0)) for dia in range(7)),
]


# --- Carga ------------------------------------------------------------------------------------------------------


def _categoria(db: Session, nombre: str, sector: str) -> Category:
    categoria = db.query(Category).filter(Category.name == nombre).first()
    if categoria is None:
        categoria = Category(name=nombre)
        db.add(categoria)
    categoria.sector = sector
    db.flush()
    return categoria


def _ingrediente(db: Session, nombre: str, cache: dict[str, Ingredient]) -> Ingredient:
    clave = nombre.lower()
    if clave not in cache:
        ingrediente = db.query(Ingredient).filter(Ingredient.name.ilike(nombre)).first()
        if ingrediente is None:
            ingrediente = Ingredient(name=nombre)
            db.add(ingrediente)
        datos = INGREDIENTES[nombre]
        # Un ingrediente del ejemplo podía estar en otra unidad (gramos, hojas): su costo ya no sirve.
        if ingrediente.unit != datos.unidad:
            ingrediente.unit = datos.unidad
            ingrediente.cost = 0
            ingrediente.extra_price = 0
        # Los costos y extras solo se cargan donde no hay ninguno: lo que el local ajustó en el panel no se pisa.
        if not ingrediente.cost:
            ingrediente.cost = datos.costo
        if not ingrediente.extra_price:
            ingrediente.extra_price = datos.extra
        db.flush()
        cache[clave] = ingrediente
    return cache[clave]


def _cargar_producto(db: Session, seccion: Seccion, categoria: Category, datos: Producto, cache: dict) -> Product:
    producto = db.query(Product).filter(Product.name == datos.nombre).first()
    if producto is None:
        producto = Product(name=datos.nombre, price=datos.precios[0], dietary_restrictions=[])
        db.add(producto)
    producto.description = datos.descripcion
    producto.category = categoria
    producto.category_id = categoria.id
    producto.sector = None
    producto.is_active = True
    producto.is_archived = False
    producto.dietary_restrictions = list(datos.restricciones)
    if seccion.variantes:
        producto.replace_variants(list(zip(seccion.variantes, datos.precios, strict=True)))
    else:
        producto.replace_variants([])
        producto.price = datos.precios[0]
    db.flush()
    if datos.receta:
        producto.replace_recipe([(_ingrediente(db, nombre, cache), cantidad) for nombre, cantidad in datos.receta])
    producto.replace_allowed_extras([_ingrediente(db, nombre, cache) for nombre in seccion.extras])
    return producto


def _cargar_menu(db: Session) -> set[str]:
    nombres: set[str] = set()
    cache: dict[str, Ingredient] = {}
    for seccion in SECCIONES:
        categoria = _categoria(db, seccion.categoria, seccion.sector)
        for datos in seccion.productos:
            _cargar_producto(db, seccion, categoria, datos, cache)
            nombres.add(datos.nombre)
        if seccion is BEBIDAS_DE_LA_CARTA:
            for bebida in BEBIDAS:
                cargar_bebida(db, categoria, bebida, actualizar=True)
                nombres.add(bebida.nombre)
    db.flush()
    return nombres


def _sacar_productos_de_ejemplo(db: Session, nombres: set[str]) -> list[str]:
    """Saca del menú los productos de ejemplo del seed: se archivan si figuran en pedidos y si no se borran."""
    sacados = []
    de_ejemplo = PRODUCTOS_DE_EJEMPLO - nombres
    for producto in db.query(Product).filter(Product.is_archived.is_(False), Product.name.in_(de_ejemplo)).all():
        try:
            catalog_service.delete_product(db, producto.id, delete_promotions=True)
        except DomainError as e:
            # Está en un pedido en curso: queda sin ofrecerse hasta que se lo borre desde el panel.
            logger.warning("No se pudo sacar '%s' del menú (%s): queda no disponible.", producto.name, e)
            with transaction(db):
                producto.is_active = False
        sacados.append(producto.name)
    return sacados


def _borrar_categorias_de_ejemplo_vacias(db: Session) -> None:
    propias = {seccion.categoria for seccion in SECCIONES}
    for categoria in db.query(Category).filter(Category.name.in_(CATEGORIAS_DE_EJEMPLO - propias)).all():
        if not any(not p.is_archived for p in categoria.products):
            categoria.release_products()
            db.delete(categoria)


def _borrar_ingredientes_de_ejemplo_sin_uso(db: Session) -> None:
    """Los ingredientes del ejemplo que La Isla no usa en ninguna receta ni como adicional."""
    for ingrediente in db.query(Ingredient).filter(Ingredient.name.in_(list(INGREDIENTES_DE_EJEMPLO))).all():
        if not ingrediente.used_in_products and not ingrediente.allowed_in_products:
            db.delete(ingrediente)


def _cargar_promos(db: Session) -> None:
    for datos in PROMOS:
        promo = db.query(Promotion).filter(Promotion.name == datos.nombre).first()
        if promo is None:
            promo = Promotion(name=datos.nombre, price=datos.precio)
            db.add(promo)
        promo.description = datos.descripcion
        promo.price = datos.precio
        promo.is_active = True
        productos = {p.name: p for p in db.query(Product).filter(Product.name.in_([n for n, _, _ in datos.productos]))}
        promo.set_products([(productos[nombre], cantidad, variante) for nombre, cantidad, variante in datos.productos])


def _cargar_local(db: Session) -> None:
    config = db.query(StoreConfig).filter(StoreConfig.id == 1).first()
    if config is None:
        config = StoreConfig(id=1)
        db.add(config)
    config.store_name = STORE_NAME
    config.address = STORE_ADDRESS
    config.contact_phone = STORE_PHONE


def cargar(db: Session) -> dict[str, int | list[str]]:
    """Carga todo y devuelve un resumen de lo que hizo."""
    with transaction(db):
        nombres = _cargar_menu(db)
    sacados = _sacar_productos_de_ejemplo(db, nombres)
    # Las relaciones cargadas antes de sacar productos quedaron viejas.
    db.expire_all()
    with transaction(db):
        _borrar_ingredientes_de_ejemplo_sin_uso(db)
        _borrar_categorias_de_ejemplo_vacias(db)
        _cargar_promos(db)
        _cargar_local(db)
    guardar_franjas(db, HORARIOS)
    return {"productos": len(nombres), "promociones": len(PROMOS), "sacados": sacados}


def run() -> None:
    db = SessionLocal()
    try:
        resumen = cargar(db)
    finally:
        db.close()
    print(
        f"Menú de La Isla cargado: {resumen['productos']} productos y {resumen['promociones']} promociones, "
        "con los datos del local y sus horarios."
    )
    if resumen["sacados"]:
        print(f"Productos que ya no se ofrecen: {', '.join(resumen['sacados'])}.")
    # Los pedidos de ejemplo se arman sobre este menú (ver app/db/seed_pedidos.py). SEED_PEDIDOS=0 los desactiva.
    if os.environ.get("SEED_PEDIDOS", "").strip() != "0":
        from app.db.seed_pedidos import run as cargar_pedidos

        cargar_pedidos()


if __name__ == "__main__":
    run()
