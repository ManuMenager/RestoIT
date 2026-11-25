"""Historial de ejemplo: repartidores, clientes y 500 pedidos sobre el menú de La Isla."""

from collections import Counter
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.db import menu_la_isla, seed, seed_pedidos
from app.models.cash_shift import CashShift
from app.models.client import Client
from app.models.delivery_driver import DeliveryDriver, DeliveryTrip
from app.models.driver_review import DriverReview
from app.models.order import Order, OrderStatus
from tests.conftest import TestingSessionLocal


@pytest.fixture()
def pedidos(db_session):
    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()
    menu_la_isla.cargar(db_session)
    creados = seed_pedidos.seed_pedidos(db_session)
    db_session.commit()
    db_session.expire_all()
    return creados, db_session.query(Order).all()


def test_carga_500_pedidos_200_clientes_y_5_repartidores(db_session, pedidos):
    creados, ordenes = pedidos

    assert (creados, len(ordenes)) == (500, 500)
    assert db_session.query(Client).count() == 200
    assert db_session.query(DeliveryDriver).count() == 5
    assert len({o.customer_phone for o in ordenes}) > 100


def test_no_agrega_pedidos_si_ya_hay(db_session, pedidos):
    assert seed_pedidos.seed_pedidos(db_session) == 0
    assert db_session.query(Order).count() == 500


def test_los_pedidos_son_variados(pedidos):
    _, ordenes = pedidos

    assert {o.status for o in ordenes} == {
        s.value for s in (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.CONFIRMED)
    }
    assert {o.source for o in ordenes} == {"web", "bot", "mostrador"}
    assert {o.channel for o in ordenes if o.source == "bot"} == {"telegram", "whatsapp"}
    assert {o.delivery_method for o in ordenes} == {"domicilio", "retiro"}
    assert {o.payment_method for o in ordenes} >= {"efectivo", "transferencia", "tarjeta", "mercadopago"}
    assert {o.scheduled_for is None for o in ordenes} == {True, False}
    assert {o.estimate_source for o in ordenes if o.scheduled_for is None} == {"smart", "fixed", "manual"}
    fechas = [o.created_at for o in ordenes]
    assert max(fechas) - min(fechas) > timedelta(days=80)
    demoras = [o.actual_minutes for o in ordenes if o.actual_minutes]
    assert min(demoras) < 25 and max(demoras) > 60


def test_los_pedidos_usan_variantes_promos_mitades_y_modificaciones(pedidos):
    _, ordenes = pedidos
    items = [item for o in ordenes for item in o.items]

    assert {"Grande", "Chica", "Carne", "Pollo"} <= {i.variant_name for i in items}
    assert any(i.promotion_id for i in items)
    assert any(i.secondary_product_id for i in items)
    assert any(i.modifications for i in items)
    assert any(i.product and i.product.category.name == "Bebidas" for i in items)


def test_los_totales_cierran_y_los_envios_solo_van_en_domicilio(pedidos):
    _, ordenes = pedidos

    for o in ordenes:
        assert o.total_amount == o.subtotal + o.shipping_cost
        assert (o.shipping_cost > 0) == (o.delivery_method == "domicilio")
        assert o.total_amount > 0


def test_el_historial_de_estados_termina_en_el_estado_del_pedido(db_session, pedidos):
    _, ordenes = pedidos

    for o in ordenes:
        eventos = sorted(o.status_events, key=lambda e: e.occurred_at)
        assert eventos[0].status == OrderStatus.CONFIRMED.value
        assert eventos[-1].status == o.status
        assert eventos[0].occurred_at.replace(tzinfo=None) == o.created_at.replace(tzinfo=None)


def test_solo_los_finalizados_tienen_demora_real_y_los_a_domicilio_repartidor(pedidos):
    _, ordenes = pedidos

    for o in ordenes:
        if o.status != OrderStatus.COMPLETED.value:
            assert o.actual_minutes is None
        if o.status == OrderStatus.COMPLETED.value and o.delivery_method == "domicilio":
            assert o.delivery_driver_id and o.trip_id and o.trip_stop
        if o.delivery_method == "retiro":
            assert o.delivery_driver_id is None


def test_hay_un_turno_cerrado_por_dia_con_su_numeracion(db_session, pedidos):
    _, ordenes = pedidos
    turnos = db_session.query(CashShift).all()

    assert len(turnos) > 60
    for turno in turnos:
        assert turno.status == "cerrada"
        assert turno.difference == turno.final_amount - turno.expected_amount
        # Los programados a futuro todavía sin turno siguen la numeración del último.
        numeros = sorted(o.shift_number for o in ordenes if o.numbering_shift_id == turno.id)
        assert numeros == list(range(1, len(numeros) + 1))


def test_hay_viajes_con_varias_paradas_y_reseñas(db_session, pedidos):
    paradas = Counter(len(v.orders) for v in db_session.query(DeliveryTrip))

    assert set(paradas) >= {1, 2}
    resenas = db_session.query(DriverReview).all()
    assert resenas and {r.rating for r in resenas} >= {1, 5}


def test_con_el_menu_de_ejemplo_no_carga_pedidos_salvo_que_se_fuerce(db_session, monkeypatch):
    def correr_seed():
        with patch.object(seed, "SessionLocal", TestingSessionLocal):
            seed.run()

    monkeypatch.delenv("SEED_PEDIDOS", raising=False)
    correr_seed()
    assert db_session.query(Order).count() == 0

    monkeypatch.setenv("SEED_PEDIDOS", "1")
    correr_seed()
    assert db_session.query(Order).count() == 500


def test_con_menu_propio_el_seed_carga_los_pedidos_y_se_puede_desactivar(db_session, monkeypatch):
    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()
    menu_la_isla.cargar(db_session)
    db_session.commit()

    monkeypatch.setenv("SEED_PEDIDOS", "0")
    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()
    assert db_session.query(Order).count() == 0

    monkeypatch.delenv("SEED_PEDIDOS")
    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()
    assert db_session.query(Order).count() == 500
