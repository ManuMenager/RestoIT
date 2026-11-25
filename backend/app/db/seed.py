import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.bebidas import BEBIDAS, Bebida
from app.db.session import SessionLocal
from app.models.menu import Category, Ingredient, Product, ProductIngredient
from app.models.store_config import StoreConfig
from app.models.user import User


def get_or_create(db: Session, model, defaults: dict | None = None, **kwargs):
    """Busca una fila por los campos en kwargs; si no existe, la crea."""
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    instance = model(**kwargs, **(defaults or {}))
    db.add(instance)
    db.flush()
    return instance, True


INGREDIENTES_DE_EJEMPLO = {
    "Salsa de tomate": "gramos",
    "Muzzarella": "gramos",
    "Albahaca": "hojas",
    "Tomate en rodajas": "gramos",
    "Ajo": "gramos",
    "Cebolla": "gramos",
    "Jamón": "gramos",
    "Morrones": "gramos",
    "Longaniza calabresa": "gramos",
    "Roquefort": "gramos",
    "Aceitunas negras": "gramos",
    "Panceta": "gramos",
    "Huevo": "unidades",
    # Postres
    "Leche": "mililitros",
    "Azúcar": "gramos",
    "Dulce de leche": "gramos",
    "Crema de leche": "mililitros",
    "Helado": "gramos",
}

# Costo por unidad de medida y precio extra de cada ingrediente del ejemplo (valores de referencia, en pesos; ver
# app/db/ingredientes.py): (costo, extra).
COSTOS_DE_EJEMPLO = {
    "Salsa de tomate": (2.5, 0),
    "Muzzarella": (9.5, 3500),
    "Albahaca": (20, 400),
    "Tomate en rodajas": (3.5, 1200),
    "Ajo": (7, 0),
    "Cebolla": (1.3, 1000),
    "Jamón": (12, 3000),
    "Morrones": (4.5, 1500),
    "Longaniza calabresa": (11, 3200),
    "Roquefort": (19, 4500),
    "Aceitunas negras": (10, 1800),
    "Panceta": (15, 3500),
    "Huevo": (350, 1200),
    "Leche": (1.4, 0),
    "Azúcar": (1.5, 0),
    "Dulce de leche": (6.5, 1500),
    "Crema de leche": (5.5, 800),
    "Helado": (7, 0),
}


def seed_ingredientes(db: Session) -> dict[str, Ingredient]:
    ingredientes = {}
    for nombre, unidad in INGREDIENTES_DE_EJEMPLO.items():
        ingrediente, _ = get_or_create(db, Ingredient, name=nombre, defaults={"unit": unidad})
        # Los costos solo se cargan donde todavía no hay ninguno: lo que el local ajustó en el panel no se pisa.
        costo, extra = COSTOS_DE_EJEMPLO[nombre]
        if not ingrediente.cost:
            ingrediente.cost = costo
        if not ingrediente.extra_price:
            ingrediente.extra_price = extra
        ingredientes[nombre] = ingrediente
    return ingredientes


PIZZAS = [
    {
        "name": "Pizza Muzzarella",
        "description": "La clásica: salsa de tomate, muzzarella y albahaca fresca.",
        "price": 8500.0,
        "preparation_time_minutes": 20,
        "dietary_restrictions": ["vegetariano"],
        "receta": [
            ("Salsa de tomate", 100),
            ("Muzzarella", 250),
            ("Albahaca", 5),
        ],
    },
    {
        "name": "Pizza Napolitana",
        "description": "Muzzarella, tomate en rodajas, ajo y albahaca.",
        "price": 9500.0,
        "preparation_time_minutes": 22,
        "dietary_restrictions": ["vegetariano"],
        "receta": [
            ("Salsa de tomate", 100),
            ("Muzzarella", 200),
            ("Tomate en rodajas", 80),
            ("Ajo", 5),
            ("Albahaca", 5),
        ],
    },
    {
        "name": "Pizza Fugazzeta",
        "description": "Doble muzzarella con abundante cebolla.",
        "price": 9800.0,
        "preparation_time_minutes": 20,
        "dietary_restrictions": ["vegetariano"],
        "receta": [
            ("Muzzarella", 300),
            ("Cebolla", 150),
        ],
    },
    {
        "name": "Pizza Especial",
        "description": "Salsa de tomate, muzzarella, jamón y morrones.",
        "price": 10500.0,
        "preparation_time_minutes": 22,
        "dietary_restrictions": [],
        "receta": [
            ("Salsa de tomate", 100),
            ("Muzzarella", 220),
            ("Jamón", 100),
            ("Morrones", 60),
        ],
    },
    {
        "name": "Pizza Calabresa",
        "description": "Muzzarella con longaniza calabresa y aceitunas negras.",
        "price": 10200.0,
        "preparation_time_minutes": 22,
        "dietary_restrictions": [],
        "receta": [
            ("Salsa de tomate", 100),
            ("Muzzarella", 220),
            ("Longaniza calabresa", 120),
            ("Aceitunas negras", 40),
        ],
    },
    {
        "name": "Pizza Roquefort",
        "description": "Muzzarella con generosas porciones de queso roquefort.",
        "price": 10800.0,
        "preparation_time_minutes": 20,
        "dietary_restrictions": ["vegetariano"],
        "receta": [
            ("Muzzarella", 220),
            ("Roquefort", 100),
        ],
    },
]


def agregar_receta(
    db: Session, producto: Product, ingredientes: dict[str, Ingredient], receta: list[tuple[str, float]]
):
    """Cada línea es (ingrediente, cantidad por unidad de producto, en la unidad del ingrediente)."""
    for nombre, cantidad in receta:
        get_or_create(
            db,
            ProductIngredient,
            defaults={"quantity": cantidad},
            product_id=producto.id,
            ingredient_id=ingredientes[nombre].id,
        )


def _crear_producto_con_receta(
    db: Session, categoria: Category, ingredientes: dict[str, Ingredient], datos: dict
) -> None:
    """Crea el producto con su receta; si ya existía no lo toca."""
    datos = dict(datos)
    receta = datos.pop("receta")
    producto, creado = get_or_create(
        db,
        Product,
        name=datos.pop("name"),
        defaults={**datos, "category_id": categoria.id},
    )
    if creado:
        agregar_receta(db, producto, ingredientes, receta)


def seed_pizzas(db: Session, categoria: Category, ingredientes: dict[str, Ingredient]):
    for datos in PIZZAS:
        _crear_producto_con_receta(db, categoria, ingredientes, datos)


POSTRES = [
    {
        "name": "Flan casero",
        "description": "Con dulce de leche y crema.",
        "price": 3500.0,
        "preparation_time_minutes": 5,
        "dietary_restrictions": ["vegetariano"],
        "receta": [("Huevo", 1), ("Leche", 120), ("Azúcar", 40), ("Dulce de leche", 30), ("Crema de leche", 30)],
    },
    {
        "name": "Helado 2 bochas",
        "description": "A elección de sabores disponibles.",
        "price": 4000.0,
        "preparation_time_minutes": 5,
        "dietary_restrictions": ["vegetariano"],
        "receta": [("Helado", 160)],
    },
]


# Las bebidas no están: son del menú de cualquier local (ver app/db/bebidas.py) y no se sacan al cargar uno propio.
PRODUCTOS_DE_EJEMPLO = {datos["name"] for datos in (*PIZZAS, *POSTRES)}
CATEGORIAS_DE_EJEMPLO = {"Pizzas", "Bebidas", "Postres"}


def cargar_bebida(db: Session, categoria: Category, bebida: Bebida, actualizar: bool = False) -> Product:
    """Crea la bebida con su imagen y su receta (una unidad de la botella como ingrediente).

    Si ya existía no la toca, salvo que `actualizar` sea True (precio y descripción pasan a ser los de la lista). La imagen
    y la receta se completan si faltan.
    """
    producto, creado = get_or_create(
        db,
        Product,
        name=bebida.nombre,
        defaults={
            "description": bebida.descripcion,
            "price": bebida.precio,
            "preparation_time_minutes": 1,
            "dietary_restrictions": [],
            "category_id": categoria.id,
        },
    )
    if actualizar and not creado:
        producto.description = bebida.descripcion
        producto.price = bebida.precio
        producto.category = categoria
        producto.is_active = True
        producto.is_archived = False
    botella, _ = get_or_create(db, Ingredient, name=bebida.nombre, defaults={"unit": "unidades", "cost": bebida.costo})
    if not botella.cost:
        botella.cost = bebida.costo
    db.flush()
    if not producto.recipe_items:
        get_or_create(db, ProductIngredient, defaults={"quantity": 1}, product_id=producto.id, ingredient_id=botella.id)
    if producto.image is None and bebida.archivo_imagen.exists():
        producto.replace_image(bebida.archivo_imagen.read_bytes(), now=datetime.now(timezone.utc))
    db.flush()
    return producto


def seed_bebidas(db: Session, categoria: Category):
    for bebida in BEBIDAS:
        cargar_bebida(db, categoria, bebida)


def seed_postres(db: Session, categoria: Category, ingredientes: dict[str, Ingredient]):
    for datos in POSTRES:
        _crear_producto_con_receta(db, categoria, ingredientes, datos)


def seed_admin(db: Session) -> User:
    """Crea la cuenta ADMIN del dueño del local a partir de las credenciales configuradas."""
    admin, _ = get_or_create(
        db,
        User,
        email=settings.ADMIN_EMAIL,
        defaults={
            "hashed_password": hash_password(settings.ADMIN_PASSWORD),
            "role": "ADMIN",
            "is_active": True,
        },
    )
    return admin


def seed_store_config(db: Session) -> StoreConfig:
    config, _ = get_or_create(
        db,
        StoreConfig,
        id=1,
        defaults={
            "store_name": "RestoIT",
            "address": "Av. Corrientes 1234, CABA",
            "contact_phone": "11 4444-5555",
            "logo_url": None,
            "theme_color": "black",
            "login_bg": "bistro",
        },
    )
    return config


def seed_menu_de_ejemplo(db: Session) -> None:
    """Menú de ejemplo de una pizzería: categorías, ingredientes y productos."""
    categoria_pizzas, _ = get_or_create(db, Category, name="Pizzas", defaults={"sector": "pizzeria"})
    categoria_pizzas.sector = "pizzeria"
    categoria_bebidas, _ = get_or_create(db, Category, name="Bebidas", defaults={"sector": "barra"})
    categoria_bebidas.sector = "barra"
    categoria_postres, _ = get_or_create(db, Category, name="Postres", defaults={"sector": "cocina"})
    categoria_postres.sector = "cocina"
    db.flush()

    ingredientes = seed_ingredientes(db)
    db.flush()

    seed_pizzas(db, categoria_pizzas, ingredientes)
    seed_bebidas(db, categoria_bebidas)
    seed_postres(db, categoria_postres, ingredientes)


def _hay_menu_propio(db: Session) -> bool:
    """Si el local ya tiene productos que no son los del ejemplo (ej. su menú real): entonces no se carga el ejemplo."""
    return db.query(Product).filter(Product.name.notin_(PRODUCTOS_DE_EJEMPLO)).first() is not None


def _seed_pedidos_de_ejemplo(db: Session, menu_propio: bool) -> int:
    """Carga el historial de ejemplo (repartidores, clientes y 500 pedidos) cuando todavía no hay pedidos.

    SEED_PEDIDOS=0 lo desactiva y SEED_PEDIDOS=1 lo fuerza también con el menú de ejemplo. Sin la variable solo se carga
    cuando el local ya tiene su propio menú (los pedidos se arman sobre él: si se cargaran antes, quedarían con
    productos que después se sacan del menú). Con el menú de ejemplo se cargan con: python -m app.db.seed_pedidos
    """
    opcion = os.environ.get("SEED_PEDIDOS", "").strip()
    if opcion == "0" or (opcion != "1" and not menu_propio):
        return 0
    from app.db.seed_pedidos import seed_pedidos

    return seed_pedidos(db)


def run():
    db = SessionLocal()
    try:
        seed_admin(db)
        seed_store_config(db)
        db.flush()

        # Se corre en cada deploy: una vez cargado el menú real del local, el de ejemplo no vuelve a aparecer.
        if _hay_menu_propio(db):
            pedidos = _seed_pedidos_de_ejemplo(db, menu_propio=True)
            db.commit()
            print(
                "Seed completado: admin y configuración (el local ya tiene su menú, no se carga el de ejemplo)."
                + (f" Pedidos de ejemplo: {pedidos}." if pedidos else "")
            )
            return
        seed_menu_de_ejemplo(db)
        pedidos = _seed_pedidos_de_ejemplo(db, menu_propio=False)

        db.commit()
        print(
            "Seed completado: admin, configuración, categorías, ingredientes y productos de la pizzería cargados."
            + (f" Pedidos de ejemplo: {pedidos}." if pedidos else "")
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
