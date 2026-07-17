import pandas as pd
import numpy as np
from faker import Faker
import random
import os
from collections import defaultdict
from datetime import datetime, timedelta

fake = Faker('es_MX')
np.random.seed(42)
random.seed(42)

N_CLIENTES   = 5000
N_VENDEDORES = 50
N_PRODUCTOS  = 128   # 16 nombres únicos x 8 categorías — sin nombres duplicados entre productos distintos
FECHA_INICIO = datetime(2021, 1, 1)
FECHA_FIN    = datetime(2024, 12, 31)
OUTPUT_DIR   = "../datos_brutos"

# Cuánto de la demanda real de un producto se traduce en cobertura de stock mínimo
PROB_MISMA_ZONA   = 0.82   # % de ventas donde el vendedor es de la misma zona que el cliente
DIAS_COBERTURA_MIN = 7
DIAS_COBERTURA_MAX = 15

os.makedirs(OUTPUT_DIR, exist_ok=True)

CATEGORIAS = {
    "Celulares":         (3000,  25000),
    "Laptops":           (8000,  45000),
    "Audio":             (500,   8000),
    "Accesorios":        (100,   2000),
    "Tablets":           (4000,  20000),
    "Gaming":            (1500,  30000),
    "Fotografía":        (2000,  35000),
    "Hogar Inteligente": (800,   12000),
}

# Versiones sucias de categorías para simular errores
CATEGORIAS_SUCIAS = [
    "celulares", "LAPTOPS", "audio ", " Accesorios",
    "tablets", "gaming", "fotografia", "hogar inteligente"
]

ZONAS     = ["Norte", "Sur", "Centro", "Este", "Oeste"]
SEGMENTOS = ["Premium", "Regular", "Ocasional"]
SEGMENTOS_SUCIOS = ["Premiun", "premiun", "REGULAR", "ocasional", "Ocacional"]

def ensuciar_fecha(fecha):
    """Devuelve la fecha en formato incorrecto DD/MM/YYYY el 15% de las veces"""
    if random.random() < 0.15:
        return fecha.strftime("%d/%m/%Y")
    return fecha.strftime("%Y-%m-%d")

def ensuciar_nombre(nombre):
    """Agrega espacios extra el 10% de las veces"""
    if random.random() < 0.10:
        return "  " + nombre + "  "
    return nombre

def ensuciar_segmento(segmento):
    """Reemplaza por versión sucia el 10% de las veces"""
    if random.random() < 0.10:
        return random.choice(SEGMENTOS_SUCIOS)
    return segmento

def ensuciar_categoria(categoria):
    """Reemplaza por versión sucia el 12% de las veces"""
    if random.random() < 0.12:
        return random.choice(CATEGORIAS_SUCIAS)
    return categoria

def ensuciar_monto(monto):
    """Genera monto negativo por error el 3% de las veces"""
    if random.random() < 0.03:
        return -abs(monto)
    return monto

def posible_nulo(valor, prob=0.05):
    """Devuelve None el prob% de las veces"""
    if random.random() < prob:
        return None
    return valor

# ── CLIENTES ──────────────────────────────────────────────────────────────────
print("Generando clientes...")
clientes = pd.DataFrame({
    "id_cliente":     [f"C{str(i).zfill(5)}" for i in range(1, N_CLIENTES + 1)],
    "nombre":         [ensuciar_nombre(fake.name()) for _ in range(N_CLIENTES)],
    "email":          [posible_nulo(fake.email(), 0.05) for _ in range(N_CLIENTES)],
    "ciudad":         [fake.city() for _ in range(N_CLIENTES)],
    "zona":           [random.choice(ZONAS) for _ in range(N_CLIENTES)],
    "segmento":       [ensuciar_segmento(random.choice(SEGMENTOS)) for _ in range(N_CLIENTES)],
    "fecha_registro": [fake.date_between(start_date="-5y", end_date="-1y") for _ in range(N_CLIENTES)],
})

# ── VENDEDORES ────────────────────────────────────────────────────────────────
print("Generando vendedores...")
vendedores = pd.DataFrame({
    "id_vendedor":   [f"V{str(i).zfill(3)}" for i in range(1, N_VENDEDORES + 1)],
    "nombre":        [ensuciar_nombre(fake.name()) for _ in range(N_VENDEDORES)],
    "zona":          [random.choice(ZONAS) for _ in range(N_VENDEDORES)],
    "fecha_ingreso": [fake.date_between(start_date="-6y", end_date="-6m") for _ in range(N_VENDEDORES)],
})

# Vendedores agrupados por zona, para poder emparejar vendedor-cliente con intención
vendedores_por_zona = {z: vendedores[vendedores["zona"] == z].reset_index(drop=True) for z in ZONAS}

def elegir_vendedor(zona_cliente):
    """82% de las veces el vendedor es de la misma zona que el cliente (venta local).
    18% de las veces es de otra zona (venta remota / cliente que viaja / referido)."""
    if random.random() < PROB_MISMA_ZONA and len(vendedores_por_zona[zona_cliente]) > 0:
        pool = vendedores_por_zona[zona_cliente]
    else:
        pool = vendedores
    return pool.sample(1).iloc[0]

NOMBRES_PRODUCTOS = {
    "Celulares": ["iPhone 15 Pro", "Samsung Galaxy S24", "Xiaomi 14 Pro", "Google Pixel 8",
                  "OnePlus 12", "Motorola Edge 50", "Realme GT5", "OPPO Find X7",
                  "Sony Xperia 1 VI", "Huawei Pura 70", "iPhone 14", "Samsung A55",
                  "Xiaomi Redmi Note 13", "Motorola G84", "Nokia G42", "Tecno Spark 20"],
    "Laptops": ["MacBook Pro M3", "Dell XPS 15", "HP Spectre x360", "Lenovo ThinkPad X1",
                "ASUS ROG Zephyrus", "Acer Swift 5", "Microsoft Surface Pro 9", "LG Gram 17",
                "Razer Blade 15", "MSI Prestige 16", "MacBook Air M2", "Dell Inspiron 15",
                "HP Pavilion 15", "Lenovo IdeaPad 5", "Acer Aspire 7", "ASUS VivoBook 16"],
    "Audio": ["Sony WH-1000XM5", "AirPods Pro 2", "Bose QC45", "Samsung Galaxy Buds2",
              "JBL Charge 5", "Beats Studio Pro", "Sennheiser HD 450", "Jabra Elite 85h",
              "Bang Olufsen H95", "Audio Technica ATH", "Sony WF-1000XM5", "Anker Q45",
              "Marshall Emberton III", "JBL Flip 6", "Bose SoundLink", "Skullcandy Crusher"],
    "Accesorios": ["Cargador MagSafe 30W", "Cable USB-C 2m", "Funda iPhone 15 Pro",
                   "Protector Pantalla S24", "Hub USB-C 7en1", "Mouse Logitech MX Master",
                   "Teclado Keychron K2", "Webcam Logitech C920", "Soporte Laptop Adjustable",
                   "Mochila Techpack 30L", "Audífonos USB-C", "Adaptador HDMI 4K",
                   "Batería Portátil 20000", "Reloj Smartwatch Band", "Pad Mouse XL Gaming",
                   "Limpiador Pantallas Kit"],
    "Tablets": ["iPad Pro M2 12.9", "Samsung Galaxy Tab S9", "iPad Air M1", "Lenovo Tab P12",
                "Xiaomi Pad 6 Pro", "Amazon Fire HD 10", "ASUS Zenpad 3S", "Huawei MatePad Pro",
                "Microsoft Surface Go 3", "iPad Mini 6", "Samsung Galaxy Tab A9", "TCL Tab 10",
                "Blackview Tab 16", "Chuwi HiPad X", "Realme Pad 2", "Honor Pad 8"],
    "Gaming": ["PlayStation 5", "Xbox Series X", "Nintendo Switch OLED", "Steam Deck 512GB",
               "Monitor LG 27GP950", "Silla Gamer DXRacer", "Headset HyperX Cloud III",
               "Teclado Razer Huntsman", "Mouse Logitech G Pro X", "Control Xbox Elite 2",
               "Capturadora Elgato 4K", "Micrófono Blue Yeti", "GPU RTX 4070 Ti",
               "RAM Corsair 32GB", "SSD Samsung 980 Pro", "Cooling Noctua NH-D15"],
    "Fotografía": ["Canon EOS R6 Mark II", "Sony Alpha 7 IV", "Nikon Z6 III",
                   "Fujifilm X-T5", "DJI Mavic 3 Pro", "GoPro Hero 12", "Lente Canon RF 50mm",
                   "Flash Godox V1", "Tripié Joby GorillaPod", "Mochila Lowepro Pro",
                   "Tarjeta SD SanDisk 256", "Batería Canon LP-E6", "Filtro ND Variable",
                   "Reflector 5en1 80cm", "Monitor Portátil 4K", "Estabilizador DJI OM6"],
    "Hogar Inteligente": ["Alexa Echo Dot 5", "Google Nest Hub 2", "Apple HomePod Mini",
                          "Foco Philips Hue", "Cámara Nest Doorbell", "Termostato Nest 3",
                          "Enchufe Inteligente TP", "Timbre Ring Video Pro", "Roomba j7 Plus",
                          "Aspiradora Dyson V15", "Cerradura Yale Smart", "Sensor Movimiento Aqara",
                          "TV Samsung QLED 55", "Proyector BenQ 4K", "Router WiFi 6 Mesh",
                          "Panel Solar Portátil"],
}

# ── PRODUCTOS (catálogo base, sin stock todavía) ───────────────────────────────
print("Generando catálogo de productos...")
productos_lista = []
categorias_nombres = list(CATEGORIAS.keys())
productos_por_cat = N_PRODUCTOS // len(categorias_nombres)

for cat in categorias_nombres:
    precio_min, precio_max = CATEGORIAS[cat]
    for j in range(productos_por_cat):
        productos_lista.append({
            "id_producto":  f"P{str(len(productos_lista)+1).zfill(4)}",
            "nombre": NOMBRES_PRODUCTOS[cat][j % len(NOMBRES_PRODUCTOS[cat])],
            "categoria":    cat,
            "precio_base":  round(random.uniform(precio_min, precio_max), 2),
        })

productos = pd.DataFrame(productos_lista)

# ── VENTAS MENSUALES ──────────────────────────────────────────────────────────
# Nota: el stock_minimo depende de la demanda real, así que las ventas se generan
# primero (en memoria) y los archivos se escriben hasta el final, una vez que
# stock_minimo ya se calculó a partir del historial completo.
print("Generando ventas por mes (48 meses)...")

id_venta   = 1
mes_actual = FECHA_INICIO
n_meses    = 0
demanda_total_por_producto = defaultdict(int)
ventas_por_archivo = []  # [(nombre_archivo, dataframe_sin_stock_minimo), ...]

while mes_actual <= FECHA_FIN:
    mes  = mes_actual.month
    anio = mes_actual.year
    n_meses += 1

    if mes in [11, 12]:
        n_ventas = random.randint(4500, 6000)
    elif mes in [7, 8]:
        n_ventas = random.randint(3500, 4500)
    elif mes in [1, 2]:
        n_ventas = random.randint(2000, 3000)
    else:
        n_ventas = random.randint(2800, 4000)

    ventas_mes = []
    for _ in range(n_ventas):
        producto = productos.sample(1).iloc[0]
        cliente  = clientes.sample(1).iloc[0]
        vendedor = elegir_vendedor(cliente["zona"])

        precio_unitario = round(producto["precio_base"] * random.uniform(0.90, 1.10), 2)
        cantidad        = random.randint(1, 5)
        descuento       = round(random.uniform(0, 0.20), 2)
        monto_total     = ensuciar_monto(round(precio_unitario * cantidad * (1 - descuento), 2))

        demanda_total_por_producto[producto["id_producto"]] += cantidad

        dias_en_mes = (mes_actual.replace(month=mes % 12 + 1, day=1) - timedelta(days=1)).day if mes < 12 else 31
        fecha_venta = mes_actual + timedelta(days=random.randint(0, dias_en_mes - 1))

        ventas_mes.append({
            "id_venta":         f"VTA{str(id_venta).zfill(7)}",
            "fecha":            ensuciar_fecha(fecha_venta),
            "mes":              mes,
            "anio":             anio,
            "id_cliente":       cliente["id_cliente"],
            "nombre_cliente":   posible_nulo(cliente["nombre"], 0.03),
            "zona_cliente":     cliente["zona"],
            "segmento_cliente": ensuciar_segmento(cliente["segmento"]),
            "id_vendedor":      vendedor["id_vendedor"],
            "nombre_vendedor":  vendedor["nombre"],
            "zona_vendedor":    vendedor["zona"],
            "id_producto":      producto["id_producto"],
            "nombre_producto":  producto["nombre"],
            "categoria":        ensuciar_categoria(producto["categoria"]),
            "precio_unitario":  precio_unitario,
            "cantidad":         posible_nulo(cantidad, 0.02),
            "descuento":        descuento,
            "monto_total":      monto_total,
        })
        id_venta += 1

    nombre_archivo = f"ventas_{anio}_{str(mes).zfill(2)}.csv"
    ventas_por_archivo.append((nombre_archivo, pd.DataFrame(ventas_mes)))
    print(f"  ✓ {nombre_archivo} generado en memoria — {n_ventas:,} registros")

    if mes == 12:
        mes_actual = datetime(anio + 1, 1, 1)
    else:
        mes_actual = datetime(anio, mes + 1, 1)

# ── STOCK MÍNIMO DERIVADO DE LA DEMANDA REAL ──────────────────────────────────
print("Calculando stock_minimo a partir de la demanda histórica real...")

def calcular_stock_minimo(id_producto):
    demanda_mensual_prom = demanda_total_por_producto.get(id_producto, 0) / n_meses
    demanda_diaria = demanda_mensual_prom / 30
    dias_cobertura = random.randint(DIAS_COBERTURA_MIN, DIAS_COBERTURA_MAX)
    return max(5, round(demanda_diaria * dias_cobertura))

productos["stock_minimo"] = productos["id_producto"].apply(calcular_stock_minimo)

# ~20% de los productos nacen por debajo del mínimo -> alertas reales de stock
def calcular_stock_actual(stock_minimo):
    if random.random() < 0.20:
        return random.randint(0, max(stock_minimo - 1, 0))
    return random.randint(stock_minimo, stock_minimo * 3)

productos["stock_actual"] = productos["stock_minimo"].apply(calcular_stock_actual)

stock_minimo_por_producto = productos.set_index("id_producto")["stock_minimo"].to_dict()

# ── ESCRITURA DE ARCHIVOS ─────────────────────────────────────────────────────
print("Escribiendo archivos mensuales con stock_minimo ya calculado...")
for nombre_archivo, df_mes in ventas_por_archivo:
    df_mes["stock_minimo"] = df_mes["id_producto"].map(stock_minimo_por_producto)
    df_mes.to_csv(os.path.join(OUTPUT_DIR, nombre_archivo), index=False, encoding="utf-8-sig")
    print(f"  ✓ {nombre_archivo} — {len(df_mes):,} registros")

# ── CATÁLOGOS ─────────────────────────────────────────────────────────────────
clientes.to_csv(os.path.join(OUTPUT_DIR, "catalogo_clientes.csv"),   index=False, encoding="utf-8-sig")
productos.to_csv(os.path.join(OUTPUT_DIR, "catalogo_productos.csv"),  index=False, encoding="utf-8-sig")
vendedores.to_csv(os.path.join(OUTPUT_DIR, "catalogo_vendedores.csv"), index=False, encoding="utf-8-sig")

# ── VALIDACIÓN RÁPIDA (se imprime, no se guarda) ──────────────────────────────
todas_ventas = pd.concat([df for _, df in ventas_por_archivo], ignore_index=True)
pct_misma_zona = (todas_ventas["zona_cliente"] == todas_ventas["zona_vendedor"]).mean() * 100

print("\n✅ Datos con errores intencionales generados:")
print(f"   - 48 archivos mensuales en /datos_brutos/")
print(f"   - Errores incluidos: fechas inconsistentes, nulos, categorías sucias,")
print(f"     espacios en nombres, montos negativos y segmentos con errores de escritura")
print(f"   - Total registros: ~{id_venta-1:,}")
print(f"   - % de ventas donde vendedor y cliente son de la misma zona: {pct_misma_zona:.1f}% (objetivo: ~{PROB_MISMA_ZONA*100:.0f}%)")
print(f"   - stock_minimo: min={productos['stock_minimo'].min()}, prom={productos['stock_minimo'].mean():.1f}, max={productos['stock_minimo'].max()}")
nombres_duplicados = productos["nombre"].value_counts()
nombres_duplicados = nombres_duplicados[nombres_duplicados > 1]
print(f"   - Nombres de producto duplicados: {len(nombres_duplicados)} (objetivo: 0)")