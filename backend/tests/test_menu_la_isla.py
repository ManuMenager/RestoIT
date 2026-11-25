"""Carga del menú de La Isla sobre una base con el menú de ejemplo del seed."""

import os
import subprocess
import sys
from datetime import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db import menu_la_isla, seed
from app.models.business_hours import BusinessHours
from app.models.menu import Category, Ingredient, Product
from app.models.order import Order, OrderItem
from app.models.promotion import Promotion
from app.models.store_config import StoreConfig
from tests.conftest import TestingSessionLocal


@pytest.fixture()
def con_menu_de_ejemplo(db_session):
    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()


def _cargar(db_session):
    resumen = menu_la_isla.cargar(db_session)
    db_session.expire_all()
    return resumen


def _producto(db_session, nombre: str) -> Product:
    return db_session.query(Product).filter(Product.name == nombre).one()


def test_carga_los_productos_con_los_precios_de_la_carta(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    muzza = _producto(db_session, "Muzzarella")
    assert [(v.name, v.price) for v in muzza.variants] == [("Grande", 16000), ("Chica", 14000)]
    assert muzza.category.name == "Pizzas"
    assert muzza.description == "Salsa, muzzarella, orégano y aceitunas."
    assert sorted(item.ingredient.name for item in muzza.recipe_items) == ["Aceitunas", "Masa de pizza", "Muzzarella", "Orégano", "Salsa"]

    calabresa = _producto(db_session, "Calabresa")
    assert [(v.name, v.price) for v in calabresa.variants] == [("Grande", 19500), ("Chica", 17500)]

    milanesa = _producto(db_session, "Milanesa Completa")
    assert [(v.name, v.price) for v in milanesa.variants] == [("Carne", 19000), ("Pollo", 17000)]

    empanada = _producto(db_session, "Empanada Carne Suave")
    assert (empanada.price, empanada.variants, empanada.category.name) == (2500, [], "Empanadas")
    assert _producto(db_session, "Fainá al Verdeo").price == 2000
    assert _producto(db_session, "Pizzaneza La Isla").price_for("Pollo") == 41000


def test_la_muzzarella_doble_lleva_el_doble_de_muzzarella(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    simple = {item.ingredient.name: item.quantity for item in _producto(db_session, "Muzzarella").recipe_items}
    doble = {item.ingredient.name: item.quantity for item in _producto(db_session, "Muzzarella Doble").recipe_items}
    assert doble["Muzzarella"] == 2 * simple["Muzzarella"]
    assert doble["Salsa"] == simple["Salsa"]
    assert db_session.query(Ingredient).filter(Ingredient.name == "Muzzarella").one().unit == "gramos"


def test_carga_todas_las_secciones_de_la_carta(db_session, con_menu_de_ejemplo):
    resumen = _cargar(db_session)

    por_categoria = {
        categoria.name: len([p for p in categoria.products if not p.is_archived])
        for categoria in db_session.query(Category).all()
    }
    assert por_categoria == {
        "Pizzas": 30,
        "Pizzas Rellenas": 7,
        "Pizzanezas": 4,
        "Fainá": 3,
        "Empanadas": 19,
        "Sándwiches": 9,
        "Papas Fritas": 2,
        "Bebidas": 17,
    }
    assert resumen["productos"] == 91


def test_saca_el_menu_de_ejemplo_y_archiva_lo_que_tiene_pedidos(db_session, con_menu_de_ejemplo):
    flan = _producto(db_session, "Flan casero")
    pedido = Order(customer_name="Ana", status="Finalizado", source="web", delivery_method="retiro", shipping_address="x")
    pedido.items = [OrderItem(product_id=flan.id, quantity=1, unit_price=3500)]
    pedido.total_amount = 3500
    db_session.add(pedido)
    db_session.commit()

    resumen = _cargar(db_session)

    assert "Pizza Muzzarella" in resumen["sacados"]
    assert db_session.query(Product).filter(Product.name == "Pizza Muzzarella").first() is None
    archivado = _producto(db_session, "Flan casero")
    assert (archivado.is_archived, archivado.category_id) == (True, None)
    assert "Postres" not in {c.name for c in db_session.query(Category)}
    assert db_session.query(Ingredient).filter(Ingredient.name == "Tomate en rodajas").first() is None


def test_no_toca_lo_cargado_a_mano(db_session, con_menu_de_ejemplo):
    propia = Category(name="Bebidas de la casa")
    db_session.add(propia)
    db_session.flush()
    db_session.add(Product(name="Limonada", price=3000, category_id=propia.id, dietary_restrictions=[]))
    db_session.add(Ingredient(name="Menta", unit="hojas"))
    db_session.commit()

    _cargar(db_session)

    assert _producto(db_session, "Limonada").is_available
    assert db_session.query(Ingredient).filter(Ingredient.name == "Menta").one()


def test_carga_las_promos_los_datos_del_local_y_los_horarios(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    tres_muzzas = db_session.query(Promotion).filter(Promotion.name == "3 Muzzarellas").one()
    assert [(it.product.name, it.quantity, it.variant_name) for it in tres_muzzas.items] == [("Muzzarella", 3, "Grande")]
    assert tres_muzzas.is_available

    config = db_session.query(StoreConfig).one()
    assert (config.store_name, config.address) == ("La Isla", "O'Higgins 999 esq. Tucumán, Quilmes Oeste")

    franjas = {(h.day_of_week, h.opens_at, h.closes_at) for h in db_session.query(BusinessHours)}
    assert (0, time(11), time(15)) in franjas
    assert (5, time(19), time(0)) in franjas
    assert (6, time(19), time(0)) in franjas
    assert (6, time(11), time(15)) not in franjas
    assert len(franjas) == 13


def test_se_puede_correr_varias_veces_sin_duplicar(db_session, con_menu_de_ejemplo):
    _cargar(db_session)
    _cargar(db_session)

    assert db_session.query(Product).filter(Product.name == "Muzzarella").count() == 1
    assert len(_producto(db_session, "Muzzarella").variants) == 2
    assert db_session.query(Promotion).count() == len(menu_la_isla.PROMOS)


def test_despues_de_cargarlo_el_seed_no_vuelve_a_traer_el_menu_de_ejemplo(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    with patch.object(seed, "SessionLocal", TestingSessionLocal):
        seed.run()
    db_session.expire_all()

    assert db_session.query(Product).filter(Product.name == "Pizza Muzzarella").first() is None
    assert db_session.query(Category).filter(Category.name == "Postres").first() is None


@pytest.mark.parametrize("modulo", ["app.db.menu_la_isla", "app.db.seed"])
def test_el_script_suelto_conoce_todos_los_modelos(modulo):
    # Se corren con "python -m" en el contenedor, sin la app ni los tests que registran todos los modelos.
    codigo = f"import {modulo}; from sqlalchemy.orm import configure_mappers; configure_mappers()"
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_las_bebidas_se_cargan_con_precio_imagen_y_receta(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    coca = _producto(db_session, "Coca-Cola 1.5L")
    assert (coca.price, coca.category.name, coca.is_available) == (6500, "Bebidas", True)
    assert coca.image is not None and coca.image.content_type == "image/png"
    assert [(item.ingredient.name, item.quantity) for item in coca.recipe_items] == [("Coca-Cola 1.5L", 1)]
    assert db_session.query(Ingredient).filter(Ingredient.name == "Coca-Cola 1.5L").one().cost == 3300
    # Las que ya estaban en el ejemplo no se duplican.
    assert db_session.query(Product).filter(Product.name == "Coca-Cola 500ml").count() == 1


def test_todos_los_productos_tienen_receta_con_costos(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    sin_receta = [p.name for p in db_session.query(Product).filter(Product.is_archived.is_(False)) if not p.recipe_items]
    assert sin_receta == []
    sin_costo = [i.name for i in db_session.query(Ingredient) if not i.cost]
    assert sin_costo == []


def test_los_ingredientes_de_la_carta_tienen_precio_extra_y_los_adicionales_permitidos(db_session, con_menu_de_ejemplo):
    _cargar(db_session)

    assert db_session.query(Ingredient).filter(Ingredient.name == "Muzzarella").one().extra_price == 3500
    adicionales = {i.name for i in _producto(db_session, "Napolitana").allowed_extras}
    assert {"Muzzarella", "Jamón", "Panceta"} <= adicionales
    assert all(i.extra_price > 0 for i in _producto(db_session, "Napolitana").allowed_extras)


def test_recargar_no_pisa_los_costos_ajustados_a_mano(db_session, con_menu_de_ejemplo):
    _cargar(db_session)
    muzza = db_session.query(Ingredient).filter(Ingredient.name == "Muzzarella").one()
    muzza.cost = 12
    db_session.commit()

    _cargar(db_session)

    assert db_session.query(Ingredient).filter(Ingredient.name == "Muzzarella").one().cost == 12
