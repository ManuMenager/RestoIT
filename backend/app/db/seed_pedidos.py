"""Datos de ejemplo de la operación del local: repartidores, clientes y pedidos de los últimos 3 meses.

    python -m app.db.seed_pedidos

Sirve para probar el panel, los reportes y las demoras estimadas con un historial creíble. Se arma sobre el menú que
tenga el local en ese momento (productos, variantes, promociones) y no hace nada si ya hay pedidos cargados. Los
resultados son siempre los mismos (semilla fija), salvo el momento "ahora" con el que se arman las fechas.

Qué incluye:
- 5 repartidores y 200 clientes con teléfono y dirección.
- 500 pedidos de los últimos 90 días: web, bot (Telegram y WhatsApp) y mostrador; a domicilio y para retirar; para ahora
  y programados; con los 4 medios de pago; finalizados, cancelados y algunos programados a futuro.
- Un turno de caja cerrado por cada día con pedidos, con sus movimientos, y los viajes de reparto con las reseñas de
  los clientes a los repartidores.
- El historial de estados de cada pedido, con el que se calculan las demoras automáticas.
"""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import base  # noqa: F401  (registra todos los modelos al correr el script solo)
from app.db.session import SessionLocal
from app.models.cash_shift import CashMovement, CashShift, CashShiftStatus, MovementType
from app.models.client import Client
from app.models.delivery_driver import DeliveryDriver, DeliveryTrip
from app.models.driver_review import DriverReview
from app.models.menu import Product
from app.models.order import (
    DeliveryMethod,
    EstimateSource,
    Order,
    OrderSource,
    OrderStatus,
    OrderStatusEvent,
    PaymentMethod,
)
from app.models.promotion import Promotion
from app.models.user import User

CANTIDAD_DE_PEDIDOS = 500
CANTIDAD_DE_CLIENTES = 200
DIAS_DE_HISTORIAL = 90
PEDIDOS_PROGRAMADOS_A_FUTURO = 6
SEMILLA = 20261125

# Argentina no tiene horario de verano: UTC-3 todo el año.
ARGENTINA = timezone(timedelta(hours=-3))

REPARTIDORES = [
    ("Matías Gómez", "11 5502-1187"),
    ("Lucas Fernández", "11 5518-4430"),
    ("Sebastián Ríos", "11 6034-9921"),
    ("Nicolás Benítez", "11 6247-0356"),
    ("Federico Acosta", "11 5390-7712"),
]

NOMBRES = [
    "Martín",
    "Lucía",
    "Santiago",
    "Valentina",
    "Mateo",
    "Camila",
    "Joaquín",
    "Sofía",
    "Tomás",
    "Agustina",
    "Facundo",
    "Julieta",
    "Nicolás",
    "Florencia",
    "Lautaro",
    "Micaela",
    "Franco",
    "Rocío",
    "Gonzalo",
    "Carolina",
    "Ezequiel",
    "Daniela",
    "Maximiliano",
    "Paula",
    "Bruno",
    "Natalia",
    "Ignacio",
    "Belén",
    "Emiliano",
    "Romina",
    "Pablo",
    "Gimena",
    "Diego",
    "Andrea",
    "Leandro",
    "Mariana",
    "Cristian",
    "Verónica",
    "Damián",
    "Luciana",
]
APELLIDOS = [
    "González",
    "Rodríguez",
    "Gómez",
    "Fernández",
    "López",
    "Díaz",
    "Martínez",
    "Pérez",
    "Romero",
    "Sánchez",
    "García",
    "Sosa",
    "Álvarez",
    "Torres",
    "Ruiz",
    "Ramírez",
    "Flores",
    "Benítez",
    "Acosta",
    "Medina",
    "Herrera",
    "Suárez",
    "Aguirre",
    "Giménez",
    "Gutiérrez",
    "Pereyra",
    "Rojas",
    "Molina",
    "Castro",
    "Ortiz",
]
CALLES = [
    "Rivadavia",
    "Mitre",
    "Av. Calchaquí",
    "Hipólito Yrigoyen",
    "San Martín",
    "Alsina",
    "Belgrano",
    "Sarmiento",
    "Moreno",
    "Lavalle",
    "Brandsen",
    "Videla",
    "Cerrito",
    "Bernardo de Irigoyen",
    "Garibaldi",
    "Tucumán",
    "O'Higgins",
    "Lamadrid",
    "Paz",
    "Allison Bell",
    "Humberto Primo",
    "Av. Vicente López",
    "Zapiola",
    "Urquiza",
]
NOTAS_DE_ENVIO = [
    "Tocar el timbre, es el departamento B.",
    "Dejar en la puerta, por favor.",
    "Casa con reja negra.",
    "Llamar al llegar, el timbre no anda.",
    "Entre calles Belgrano y Sarmiento.",
]
NOTAS_DE_COCINA = [
    "Bien cocida, por favor.",
    "Cortar en 12 porciones.",
    "Sin cubiertos.",
    "Una de las pizzas sin orégano.",
    "Pago con $20.000, necesito vuelto.",
    "Es un cumpleaños, si pueden mandar velitas.",
]
COMENTARIOS_DE_RESEÑA = {
    5: ["Muy amable y rápido.", "Llegó caliente, excelente.", "Todo perfecto.", None, None],
    4: ["Buen servicio.", "Un poquito de demora pero muy atento.", None],
    3: ["Llegó tibio.", "Normal, sin problemas."],
    2: ["Tardó bastante más de lo prometido."],
    1: ["No encontraba la dirección y llegó muy tarde.", "El pedido llegó frío."],
}

# Qué lleva cada tipo de pedido: (peso del perfil, [(categoría, (mín, máx) de unidades por producto, probabilidad)]).
# Las categorías que el menú no tenga se saltean.
PERFILES: list[tuple[int, list[tuple[str, tuple[int, int], float]]]] = [
    (46, [("Pizzas", (1, 3), 1.0), ("Bebidas", (1, 2), 0.8), ("Empanadas", (3, 12), 0.25), ("Fainá", (1, 2), 0.12)]),
    (14, [("Empanadas", (6, 24), 1.0), ("Bebidas", (1, 2), 0.6)]),
    (10, [("Sándwiches", (1, 2), 1.0), ("Papas Fritas", (1, 1), 0.5), ("Bebidas", (1, 2), 0.75)]),
    (6, [("Pizzanezas", (1, 2), 1.0), ("Bebidas", (1, 2), 0.8)]),
    (6, [("Pizzas Rellenas", (1, 2), 1.0), ("Bebidas", (1, 1), 0.7), ("Postres", (1, 2), 0.3)]),
    (8, [("Pizzas", (1, 2), 0.7), ("Empanadas", (3, 12), 0.7), ("Bebidas", (1, 3), 0.9)]),
    (4, [("Postres", (1, 3), 1.0), ("Bebidas", (1, 2), 0.5)]),
]
PROBABILIDAD_DE_PROMO = 0.12
PROBABILIDAD_DE_MITAD_Y_MITAD = 0.18
PROBABILIDAD_DE_MODIFICACION = 0.15

# Peso de cada día de la semana (0 = lunes): el fin de semana se vende más.
PESO_POR_DIA = [0.7, 0.7, 0.8, 0.95, 1.35, 1.6, 1.45]
PROBABILIDAD_DE_CANCELACION = 0.06
PROBABILIDAD_DE_PROGRAMADO = 0.15


@dataclass
class _Plan:
    """Un pedido por crear, con todos sus datos y los momentos de su historial."""

    cliente: Client
    fuente: OrderSource
    entrega: DeliveryMethod
    creado: datetime
    estado: OrderStatus
    lineas: list[tuple]
    envio: Decimal
    programado: datetime | None = None
    canal: str | None = None
    chat_id: str | None = None
    medio_de_pago: PaymentMethod | None = None
    notas: str | None = None
    direccion: str | None = None
    # Hasta que el pedido está listo (cocina) y los momentos de cada cambio de estado.
    preparacion: int = 20
    listo: datetime | None = None
    eventos: list[tuple[OrderStatus, datetime]] = field(default_factory=list)
    repartidor: DeliveryDriver | None = None
    viaje: "_Viaje | None" = None
    parada: int | None = None
    estimado: int | None = None
    origen_estimado: EstimateSource | None = None
    pedido: Order | None = None


@dataclass
class _Viaje:
    repartidor: DeliveryDriver
    salida: datetime
    pedidos: list[_Plan] = field(default_factory=list)
    trip: DeliveryTrip | None = None


# --- Repartidores y clientes ---------------------------------------------------------------------------------------


def seed_repartidores(db: Session) -> list[DeliveryDriver]:
    repartidores = []
    for nombre, telefono in REPARTIDORES:
        repartidor = db.query(DeliveryDriver).filter(DeliveryDriver.name == nombre).first()
        if repartidor is None:
            repartidor = DeliveryDriver(name=nombre, phone=telefono, is_active=True)
            db.add(repartidor)
        repartidores.append(repartidor)
    db.flush()
    return repartidores


def seed_clientes(db: Session, rng: random.Random, cantidad: int = CANTIDAD_DE_CLIENTES) -> list[Client]:
    """Clientes con nombre, teléfono (celular de Buenos Aires) y dirección. Los que ya estén (mismo teléfono) se reusan."""
    clientes: list[Client] = []
    telefonos: set[str] = set()
    nombres: set[str] = set()
    while len(clientes) < cantidad:
        nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)}"
        telefono = Client.normalize_phone(f"11 {rng.randint(2000, 6999)}-{rng.randint(1000, 9999)}")
        if nombre in nombres or telefono in telefonos:
            continue
        nombres.add(nombre)
        telefonos.add(telefono)
        direccion = f"{rng.choice(CALLES)} {rng.randint(100, 3500)}"
        if rng.random() < 0.25:
            direccion += f", piso {rng.randint(1, 9)} depto {rng.choice('ABCD')}"
        cliente = db.query(Client).filter(Client.phone == telefono).first()
        if cliente is None:
            cliente = Client(phone=telefono, full_name=nombre, address=direccion)
            db.add(cliente)
        clientes.append(cliente)
    db.flush()
    return clientes


# --- Armado de los pedidos -----------------------------------------------------------------------------------------


def _hora_local(rng: random.Random, dia: date) -> datetime:
    """Un momento del día en que el local recibe pedidos: mediodía (menos movido, de lunes a sábado) o noche."""
    if dia.weekday() != 6 and rng.random() < 0.3:
        hora = rng.triangular(11.5, 14.5, 13.0)
    else:
        hora = rng.triangular(19.5, 23.5, 21.0)
    return datetime(dia.year, dia.month, dia.day, tzinfo=ARGENTINA) + timedelta(hours=hora)


def _dias_con_peso(hoy: date) -> tuple[list[date], list[float]]:
    # Del día anterior hacia atrás; el negocio crece de a poco, así que lo reciente pesa un poco más.
    dias = [hoy - timedelta(days=n) for n in range(1, DIAS_DE_HISTORIAL + 1)]
    pesos = [
        PESO_POR_DIA[d.weekday()] * (0.7 + 0.5 * (DIAS_DE_HISTORIAL - n) / DIAS_DE_HISTORIAL)
        for n, d in enumerate(dias)
    ]
    return dias, pesos


class _Catalogo:
    """Lo que se puede pedir hoy: productos por categoría, y promociones disponibles."""

    def __init__(self, db: Session):
        self.por_categoria: dict[str, list[Product]] = defaultdict(list)
        for producto in db.query(Product).filter(Product.is_available).order_by(Product.id):
            self.por_categoria[producto.category.name].append(producto)
        self.promociones = [p for p in db.query(Promotion).order_by(Promotion.id) if p.is_available]
        if not self.por_categoria:
            raise RuntimeError("No hay productos disponibles: cargá el menú antes de generar los pedidos.")

    def productos(self, categoria: str) -> list[Product]:
        return self.por_categoria.get(categoria, [])

    def cualquiera(self, rng: random.Random) -> Product:
        return rng.choice(rng.choice(list(self.por_categoria.values())))


def _variante(rng: random.Random, producto: Product) -> str | None:
    if not producto.variants:
        return None
    pesos = [60, 40, 20][: len(producto.variants)]
    return rng.choices([v.name for v in producto.variants], weights=pesos)[0]


def _modificacion(rng: random.Random, producto: Product) -> list[dict]:
    """Un "sin ..." de la receta o un adicional permitido (con su precio extra), como los arma el bot."""
    adicionales = [i for i in producto.allowed_extras if i.extra_price and i.extra_price > 0]
    if adicionales and rng.random() < 0.55:
        ingrediente = rng.choice(adicionales)
        return [
            {
                "type": "positive",
                "action": "add",
                "ingredient_id": ingrediente.id,
                "name": ingrediente.name.lower(),
                "price": float(ingrediente.extra_price),
                "tag": f"[EXTRA {ingrediente.name.upper()}]",
            }
        ]
    # No se le saca la masa ni la salsa: es lo que hace al producto.
    quitables = [
        i.ingredient
        for i in producto.recipe_items
        if i.ingredient.name not in ("Masa de pizza", "Salsa", "Tapa de empanada")
    ]
    if not quitables:
        return []
    ingrediente = rng.choice(quitables)
    return [
        {
            "type": "negative",
            "action": "remove",
            "ingredient_id": ingrediente.id,
            "name": ingrediente.name.lower(),
            "tag": f"[SIN {ingrediente.name.upper()}]",
        }
    ]


def _lineas_de_pizza(rng: random.Random, catalogo: _Catalogo, pizzas: list[Product], cantidad: int) -> list[tuple]:
    producto = rng.choice(pizzas)
    variante = _variante(rng, producto)
    if len(pizzas) > 1 and rng.random() < PROBABILIDAD_DE_MITAD_Y_MITAD:
        otras = [p for p in pizzas if p.id != producto.id and (variante is None or p.variant_named(variante))]
        if otras:
            return [(producto, cantidad, rng.choice(otras), None, None, None, variante)]
    modificaciones = _modificacion(rng, producto) if rng.random() < PROBABILIDAD_DE_MODIFICACION else None
    return [(producto, cantidad, None, None, modificaciones, None, variante)]


def _lineas(rng: random.Random, catalogo: _Catalogo) -> list[tuple]:
    if catalogo.promociones and rng.random() < PROBABILIDAD_DE_PROMO:
        lineas: list[tuple] = [(None, rng.choice([1, 1, 1, 2]), None, None, None, rng.choice(catalogo.promociones))]
        if catalogo.productos("Bebidas") and rng.random() < 0.4:
            lineas.append((rng.choice(catalogo.productos("Bebidas")), 1))
        return lineas

    perfil = rng.choices(PERFILES, weights=[p[0] for p in PERFILES])[0][1]
    lineas = []
    for categoria, (minimo, maximo), probabilidad in perfil:
        productos = catalogo.productos(categoria)
        if not productos or rng.random() > probabilidad:
            continue
        if categoria == "Pizzas":
            for _ in range(rng.choices(range(minimo, maximo + 1), weights=[55, 30, 15][: maximo - minimo + 1])[0]):
                lineas += _lineas_de_pizza(rng, catalogo, productos, rng.choices([1, 2], weights=[85, 15])[0])
        elif categoria == "Empanadas":
            total = rng.randint(minimo, maximo)
            # Como mucho 20 unidades de un mismo gusto por pedido.
            gustos = rng.sample(productos, min(len(productos), max(rng.randint(1, 4), -(-total // 20))))
            for i, gusto in enumerate(gustos):
                cantidad = total // len(gustos) + (1 if i < total % len(gustos) else 0)
                if cantidad:
                    lineas.append((gusto, cantidad))
        else:
            elegidos = rng.sample(productos, min(len(productos), rng.randint(1, 2)))
            for producto in elegidos:
                lineas.append((producto, rng.randint(minimo, maximo), None, None, None, None, _variante(rng, producto)))
    if not lineas:
        producto = catalogo.cualquiera(rng)
        lineas = [(producto, 1, None, None, None, None, _variante(rng, producto))]
    return lineas


def _medio_de_pago(rng: random.Random, fuente: OrderSource) -> PaymentMethod:
    pesos = {
        OrderSource.WEB: (25, 20, 20, 35),
        OrderSource.BOT: (40, 30, 10, 20),
        OrderSource.COUNTER: (45, 15, 35, 5),
    }[fuente]
    metodos = [PaymentMethod.CASH, PaymentMethod.TRANSFER, PaymentMethod.CARD, PaymentMethod.MERCADOPAGO]
    return rng.choices(metodos, weights=pesos)[0]


def _redondear(momento: datetime, minutos: int = 15) -> datetime:
    extra = (-(momento.minute % minutos)) % minutos
    return (momento + timedelta(minutes=extra)).replace(second=0, microsecond=0)


def _planear(
    rng: random.Random, clientes: list[Client], catalogo: _Catalogo, hoy: date, ahora: datetime, cantidad: int
) -> list[_Plan]:
    dias, pesos = _dias_con_peso(hoy)
    # Hay clientes que piden seguido y otros una sola vez.
    pesos_clientes = [1 / (1 + i) ** 0.6 for i in range(len(clientes))]
    planes: list[_Plan] = []

    for numero in range(cantidad):
        a_futuro = numero >= cantidad - PEDIDOS_PROGRAMADOS_A_FUTURO
        cliente = rng.choices(clientes, weights=pesos_clientes)[0]
        fuente = rng.choices([OrderSource.WEB, OrderSource.BOT, OrderSource.COUNTER], weights=[40, 30, 30])[0]
        entrega = (
            DeliveryMethod.DELIVERY
            if rng.random() < (0.45 if fuente == OrderSource.COUNTER else 0.7)
            else DeliveryMethod.PICKUP
        )
        envio = (
            Decimal(rng.choice([1500, 2000, 2000, 2500, 3000])) if entrega == DeliveryMethod.DELIVERY else Decimal(0)
        )

        if a_futuro:
            # Pedidos de ayer a la noche para mañana o pasado: todavía sin preparar.
            creado = ahora - timedelta(hours=rng.randint(2, 20))
            dia = hoy + timedelta(days=rng.randint(1, 2))
            programado = _redondear(_hora_local(rng, dia).astimezone(timezone.utc), 15)
            estado = OrderStatus.CONFIRMED
        else:
            dia = rng.choices(dias, weights=pesos)[0]
            momento = _hora_local(rng, dia).astimezone(timezone.utc)
            programado = None
            if rng.random() < PROBABILIDAD_DE_PROGRAMADO:
                # Se pidió antes (entre 1 y 5 horas) para que llegue a un horario puntual.
                programado = _redondear(momento, 15)
                creado = programado - timedelta(hours=rng.uniform(1, 5), minutes=rng.randint(0, 59))
            else:
                creado = momento
            estado = OrderStatus.CANCELLED if rng.random() < PROBABILIDAD_DE_CANCELACION else OrderStatus.COMPLETED

        plan = _Plan(
            cliente=cliente,
            fuente=fuente,
            entrega=entrega,
            creado=creado.replace(microsecond=0),
            estado=estado,
            lineas=_lineas(rng, catalogo),
            envio=envio,
            programado=programado,
            direccion=cliente.address if rng.random() < 0.9 else f"{rng.choice(CALLES)} {rng.randint(100, 3500)}",
        )
        if fuente == OrderSource.BOT:
            plan.canal = rng.choices(["whatsapp", "telegram"], weights=[60, 40])[0]
            plan.chat_id = str(rng.randint(10**8, 10**9)) if plan.canal == "telegram" else f"549{cliente.phone}"
        if estado == OrderStatus.COMPLETED:
            plan.medio_de_pago = _medio_de_pago(rng, fuente)
        elif a_futuro and rng.random() < 0.4:
            plan.medio_de_pago = PaymentMethod.MERCADOPAGO
        if rng.random() < 0.12:
            plan.notas = rng.choice(
                NOTAS_DE_ENVIO if entrega == DeliveryMethod.DELIVERY and rng.random() < 0.6 else NOTAS_DE_COCINA
            )

        # Demora de cocina: más lenta en los horarios pico de la noche y cuando el pedido es grande.
        hora = (plan.programado or plan.creado).astimezone(ARGENTINA).hour
        pico = 1.3 if hora >= 20 else 1.0
        unidades = sum(linea[1] for linea in plan.lineas)
        plan.preparacion = int((rng.randint(12, 28) + min(unidades, 12)) * pico)
        if programado is None and estado != OrderStatus.CONFIRMED:
            plan.estimado = rng.randint(40, 70) if entrega == DeliveryMethod.DELIVERY else rng.randint(20, 40)
            plan.origen_estimado = rng.choices(
                [EstimateSource.SMART, EstimateSource.FIXED, EstimateSource.MANUAL], weights=[45, 35, 20]
            )[0]
        planes.append(plan)

    planes.sort(key=lambda p: p.creado)
    return planes


def _armar_historial(rng: random.Random, planes: list[_Plan], repartidores: list[DeliveryDriver]) -> list[_Viaje]:
    """Los momentos de cada cambio de estado y los viajes de los repartidores (hasta 3 pedidos por viaje)."""
    for plan in planes:
        inicio = plan.programado - timedelta(minutes=plan.preparacion + 10) if plan.programado else plan.creado
        plan.listo = inicio + timedelta(minutes=plan.preparacion)
        plan.eventos = [(OrderStatus.CONFIRMED, plan.creado)]

    for plan in planes:
        if plan.estado == OrderStatus.CANCELLED:
            plan.eventos.append((OrderStatus.CANCELLED, plan.creado + timedelta(minutes=rng.randint(3, 25))))
        elif plan.estado == OrderStatus.COMPLETED and plan.entrega == DeliveryMethod.PICKUP:
            plan.eventos.append((OrderStatus.READY_FOR_PICKUP, plan.listo))
            plan.eventos.append((OrderStatus.COMPLETED, plan.listo + timedelta(minutes=rng.randint(2, 20))))

    entregas = sorted(
        (p for p in planes if p.estado == OrderStatus.COMPLETED and p.entrega == DeliveryMethod.DELIVERY),
        key=lambda p: p.listo,
    )
    viajes: list[_Viaje] = []
    libre_desde: dict[int, datetime] = {r.id: datetime.min.replace(tzinfo=timezone.utc) for r in repartidores}
    # Hay repartidores que trabajan más que otros.
    carga = [4, 3, 3, 2, 1]
    actual: _Viaje | None = None
    for plan in entregas:
        if actual and len(actual.pedidos) < 3 and plan.listo - actual.pedidos[0].listo <= timedelta(minutes=12):
            actual.pedidos.append(plan)
            actual.salida = max(actual.salida, plan.listo + timedelta(minutes=3))
            continue
        disponibles = [r for r in repartidores if libre_desde[r.id] <= plan.listo]
        candidatos = disponibles or [min(repartidores, key=lambda r: libre_desde[r.id])]
        repartidor = rng.choices(candidatos, weights=[carga[repartidores.index(r)] for r in candidatos])[0]
        salida = max(plan.listo + timedelta(minutes=3), libre_desde[repartidor.id])
        actual = _Viaje(repartidor, salida, [plan])
        viajes.append(actual)
        # El repartidor se ocupa hasta que vuelve: se aproxima por la cantidad de paradas, así que se recalcula abajo.
        libre_desde[repartidor.id] = salida + timedelta(minutes=30)

    for viaje in viajes:
        for parada, plan in enumerate(viaje.pedidos, start=1):
            plan.viaje = viaje
            plan.parada = parada
            plan.repartidor = viaje.repartidor
            plan.eventos.append((OrderStatus.ON_THE_WAY, viaje.salida))
            plan.eventos.append(
                (OrderStatus.COMPLETED, viaje.salida + timedelta(minutes=8 * parada + rng.randint(0, 7)))
            )
    return viajes


# --- Carga ---------------------------------------------------------------------------------------------------------


def _crear_pedido(plan: _Plan, turno: CashShift | None) -> Order:
    pedido = Order(
        customer_name=plan.cliente.full_name,
        customer_phone=plan.cliente.phone,
        source=plan.fuente.value,
        channel=plan.canal,
        chat_id=plan.chat_id,
        status=plan.estado.value,
        notes=plan.notas,
        created_at=plan.creado,
        scheduled_for=plan.programado,
        estimated_minutes=plan.estimado,
        estimate_source=plan.origen_estimado.value if plan.origen_estimado else None,
        cash_shift=turno,
        cash_shift_id=turno.id if turno else None,
        delivery_driver=plan.repartidor,
    )
    pedido.shipping_cost = plan.envio
    pedido.set_delivery(plan.entrega, plan.direccion)
    pedido.set_items(plan.lineas)

    entregado = plan.estado == OrderStatus.COMPLETED
    for item in pedido.items:
        item.is_prepared = entregado
    if plan.medio_de_pago:
        pedido.payment_method = plan.medio_de_pago.value
        pedido.is_paid = entregado or plan.medio_de_pago == PaymentMethod.MERCADOPAGO
        if plan.medio_de_pago == PaymentMethod.MERCADOPAGO:
            pedido.mp_preference_id = f"seed-pref-{plan.creado:%Y%m%d%H%M%S}-{plan.cliente.id}"
            if pedido.is_paid:
                pedido.mp_payment_id = f"seed-pay-{plan.creado:%Y%m%d%H%M%S}-{plan.cliente.id}"
    if entregado and plan.programado is None:
        final = max(momento for estado, momento in plan.eventos if estado == OrderStatus.COMPLETED)
        pedido.actual_minutes = max(1, round((final - plan.creado).total_seconds() / 60))
    if plan.viaje is not None:
        pedido.trip_stop = plan.parada
        pedido.eta_minutes = 8 * plan.parada + 5
    return pedido


def _crear_turnos(db: Session, rng: random.Random, planes: list[_Plan], admin: User | None) -> dict[date, CashShift]:
    """Un turno de caja por cada día con pedidos (los pasados), abierto antes del primero y cerrado después del último."""
    por_dia: dict[date, list[_Plan]] = defaultdict(list)
    for plan in planes:
        if plan.estado != OrderStatus.CONFIRMED:
            por_dia[plan.creado.astimezone(ARGENTINA).date()].append(plan)
    turnos: dict[date, CashShift] = {}
    for dia in sorted(por_dia):
        momentos = [m for p in por_dia[dia] for _, m in p.eventos]
        abierto = min(momentos) - timedelta(minutes=rng.randint(20, 60))
        cerrado = max(momentos) + timedelta(minutes=rng.randint(20, 60))
        turno = CashShift(
            opened_at=abierto,
            closed_at=cerrado,
            initial_amount=rng.choice([15000, 20000, 25000, 30000]),
            status=CashShiftStatus.CLOSED.value,
            opened_by_id=admin.id if admin else None,
            closed_by_id=admin.id if admin else None,
        )
        db.add(turno)
        turnos[dia] = turno
    db.flush()
    return turnos


def _cerrar_turnos(db: Session, rng: random.Random, turnos: dict[date, CashShift]) -> None:
    """Caja teórica = fondo inicial + efectivo cobrado − egresos del turno; el contado casi siempre coincide."""
    for turno in turnos.values():
        efectivo = sum(
            (o.total_amount for o in turno.orders if o.payment_method == PaymentMethod.CASH.value and o.is_paid),
            Decimal(0),
        )
        egresos = Decimal(0)
        for _ in range(rng.choices([0, 1, 2], weights=[45, 40, 15])[0]):
            monto = Decimal(rng.randrange(5000, 40001, 500))
            egresos += monto
            db.add(
                CashMovement(
                    cash_shift_id=turno.id,
                    amount=monto,
                    type=MovementType.EXPENSE.value,
                    category=rng.choice(["Compra de insumos", "Pago a proveedor", "Gas", "Limpieza"]),
                    created_at=turno.opened_at + timedelta(hours=rng.randint(1, 5)),
                    created_by_id=turno.opened_by_id,
                )
            )
        esperado = turno.initial_amount + efectivo - egresos
        diferencia = Decimal(rng.choices([0, -500, -1000, 500, 1000, -2000], weights=[70, 8, 6, 8, 5, 3])[0])
        turno.expected_amount = esperado
        turno.final_amount = esperado + diferencia
        turno.difference = diferencia


def _reemplazar_historial(db: Session, rng: random.Random, planes: list[_Plan]) -> None:
    """Cambia el historial que se registra solo al guardar (con la hora actual) por el real de cada pedido."""
    ids = [p.pedido.id for p in planes if p.pedido]
    db.query(OrderStatusEvent).filter(OrderStatusEvent.order_id.in_(ids)).delete(synchronize_session=False)
    for plan in planes:
        for estado, momento in sorted(plan.eventos, key=lambda e: e[1]):
            hora = momento.astimezone(ARGENTINA).hour
            cola = rng.randint(2, 7) if 20 <= hora <= 23 else rng.randint(0, 3)
            db.add(OrderStatusEvent(order_id=plan.pedido.id, status=estado.value, occurred_at=momento, queue_size=cola))


def _reseñas(db: Session, rng: random.Random, planes: list[_Plan]) -> None:
    for plan in planes:
        if plan.repartidor is None or plan.estado != OrderStatus.COMPLETED or rng.random() > 0.35:
            continue
        final = max(m for e, m in plan.eventos if e == OrderStatus.COMPLETED)
        puntaje = rng.choices([5, 4, 3, 2, 1], weights=[50, 25, 12, 8, 5])[0]
        db.add(
            DriverReview(
                delivery_driver_id=plan.repartidor.id,
                order_id=plan.pedido.id,
                rating=puntaje,
                comment=rng.choice(COMENTARIOS_DE_RESEÑA[puntaje]),
                created_at=final + timedelta(minutes=rng.randint(5, 240)),
            )
        )


def seed_pedidos(
    db: Session,
    cantidad: int = CANTIDAD_DE_PEDIDOS,
    clientes: int = CANTIDAD_DE_CLIENTES,
    ahora: datetime | None = None,
) -> int:
    """Carga repartidores, clientes y pedidos. Devuelve cuántos pedidos creó (0 si ya había pedidos)."""
    if db.query(Order).first() is not None:
        return 0
    rng = random.Random(SEMILLA)
    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(ARGENTINA).date()

    catalogo = _Catalogo(db)
    repartidores = seed_repartidores(db)
    lista_de_clientes = seed_clientes(db, rng, clientes)
    planes = _planear(rng, lista_de_clientes, catalogo, hoy, ahora, cantidad)
    viajes = _armar_historial(rng, planes, repartidores)
    admin = db.query(User).filter(User.role == "ADMIN").first()
    turnos = _crear_turnos(db, rng, planes, admin)

    for viaje in viajes:
        viaje.trip = DeliveryTrip(
            driver=viaje.repartidor, dispatched_at=viaje.salida, total_minutes=8 * len(viaje.pedidos) + 8
        )
        db.add(viaje.trip)
    db.flush()

    for plan in planes:
        dia = plan.creado.astimezone(ARGENTINA).date()
        pedido = _crear_pedido(plan, turnos.get(dia) if plan.estado != OrderStatus.CONFIRMED else None)
        if plan.viaje is not None:
            pedido.trip = plan.viaje.trip
        plan.pedido = pedido
        db.add(pedido)
        if len(db.new) > 200:
            db.flush()
    db.flush()

    _reemplazar_historial(db, rng, planes)
    _reseñas(db, rng, planes)
    db.flush()
    db.expire_all()
    _cerrar_turnos(db, rng, turnos)
    db.flush()
    return len(planes)


def run() -> None:
    db = SessionLocal()
    try:
        creados = seed_pedidos(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    if creados:
        print(
            f"Pedidos de ejemplo cargados: {creados}, con {CANTIDAD_DE_CLIENTES} clientes y {len(REPARTIDORES)} repartidores."
        )
    else:
        print("Ya hay pedidos cargados: no se agregó ninguno.")


if __name__ == "__main__":
    run()
