import os
import json
import time
from datetime import date, timedelta

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL_LOGIN      = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_CONSUMOS   = "https://cloud.dazsistemas.com.ar/stock/Consumos_Mensuales.aspx"
SPREADSHEET_ID = "1u7cckay0IJ60bfoKk2OZo-TjCvTbH9O1wKxNFdSKDCQ"
HOJA           = "GASTOS REPARACIONES"

USUARIO          = os.environ["CUBIERTAS_USUARIO"]
PASSWORD         = os.environ["CUBIERTAS_PASSWORD"]
GOOGLE_CREDS_RAW = os.environ["GOOGLE_CREDENTIALS"]

GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
GMAIL_DEST        = os.environ["GMAIL_DEST"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def crear_driver():
    opciones = Options()
    opciones.add_argument("--headless=new")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--disable-gpu")
    opciones.add_argument("--window-size=1920,1400")
    return webdriver.Chrome(options=opciones)


def login(driver):
    driver.get(URL_LOGIN)
    wait = WebDriverWait(driver, 20)
    campo_usuario = wait.until(EC.presence_of_element_located((By.ID, "txtUsuario")))
    campo_password = driver.find_element(By.ID, "txtPass")
    campo_usuario.send_keys(USUARIO)
    campo_password.send_keys(PASSWORD)
    driver.find_element(By.ID, "btnLogin").click()
    wait.until(EC.url_contains("/menu/"))


def _entrar_stock(driver):
    wait = WebDriverWait(driver, 20)
    wait.until(lambda d: d.execute_script("return typeof openLink === 'function';"))
    ventanas_antes = set(driver.window_handles)
    driver.execute_script("openLink('W255TK', '853', '/stock/Login.aspx?empresa=853');")
    time.sleep(3)
    ventanas_despues = set(driver.window_handles)
    nuevas = ventanas_despues - ventanas_antes
    if nuevas:
        driver.switch_to.window(nuevas.pop())
    wait.until(EC.url_contains("/stock/"))
    time.sleep(2)


def mes_anterior():
    hoy = date.today()
    primer_dia = hoy.replace(day=1)
    ultimo_mes = primer_dia - timedelta(days=1)
    return ultimo_mes.month, ultimo_mes.year


def buscar_consumos(driver, mes, anio):
    driver.get(URL_CONSUMOS)
    wait = WebDriverWait(driver, 20)

    # Esperar que cargue el formulario
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='number']")))
    time.sleep(1)

    # Buscar campos de mes y año por nombre/id
    campo_mes = driver.find_element(
        By.XPATH,
        "//input[contains(@id,'Mes') or contains(@name,'Mes') or contains(@id,'mes') or contains(@name,'mes')]"
    )
    campo_anio = driver.find_element(
        By.XPATH,
        "//input[contains(@id,'Anio') or contains(@name,'Anio') or contains(@id,'Año') or "
        "contains(@name,'Año') or contains(@id,'anio') or contains(@name,'Year') or contains(@id,'Year')]"
    )

    campo_mes.triple_click() if hasattr(campo_mes, 'triple_click') else None
    campo_mes.clear()
    campo_mes.send_keys(str(mes).zfill(2))
    campo_anio.clear()
    campo_anio.send_keys(str(anio))

    # Buscar botón Buscar
    boton = driver.find_element(
        By.XPATH,
        "//a[contains(normalize-space(),'Buscar')] | //input[@value='Buscar'] | "
        "//button[contains(normalize-space(),'Buscar')]"
    )
    boton.click()

    wait.until(EC.url_contains("Reportes"))
    time.sleep(4)


def _extraer_tabla_actual(driver):
    """Extrae filas con patente y total de la página actual del reporte."""
    filas = []

    # Buscar iframes y cambiar contexto si es necesario
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    contextos = [None] + iframes

    for ctx in contextos:
        if ctx is not None:
            try:
                driver.switch_to.frame(ctx)
            except Exception:
                continue
        else:
            driver.switch_to.default_content()

        tablas = driver.find_elements(By.TAG_NAME, "table")
        for tabla in tablas:
            encabezados = tabla.find_elements(By.TAG_NAME, "th")
            textos_enc = [e.text.strip() for e in encabezados]
            if "Patente" not in textos_enc:
                # Intentar con primera fila como encabezado
                filas_tabla = tabla.find_elements(By.TAG_NAME, "tr")
                if not filas_tabla:
                    continue
                primera = [td.text.strip() for td in filas_tabla[0].find_elements(By.TAG_NAME, "td")]
                if "Patente" not in primera:
                    continue
                textos_enc = primera
                filas_datos = filas_tabla[1:]
            else:
                filas_datos = tabla.find_elements(By.TAG_NAME, "tr")[1:]

            idx_patente = textos_enc.index("Patente")
            idx_total   = textos_enc.index("Total") if "Total" in textos_enc else len(textos_enc) - 1

            for fila in filas_datos:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) <= max(idx_patente, idx_total):
                    continue
                patente   = celdas[idx_patente].text.strip()
                total_txt = celdas[idx_total].text.strip()
                if not patente:
                    continue
                total_limpio = total_txt.replace(".", "").replace(",", ".").replace("$", "").strip()
                try:
                    total_num = float(total_limpio)
                except ValueError:
                    total_num = 0.0
                filas.append((patente, total_num))

            if filas:
                break
        if filas:
            break

    driver.switch_to.default_content()
    return filas


def extraer_todos_los_datos(driver):
    todos = []
    pagina = 1

    while True:
        filas = _extraer_tabla_actual(driver)
        todos.extend(filas)

        # Intentar ir a la siguiente página
        try:
            boton_siguiente = driver.find_element(
                By.XPATH,
                "//input[@title='Next Page'] | //a[@title='Next Page'] | "
                "//input[@title='Página siguiente'] | //a[@title='Página siguiente']"
            )
            if boton_siguiente.get_attribute("disabled") or not boton_siguiente.is_enabled():
                break
            boton_siguiente.click()
            time.sleep(3)
            pagina += 1
        except Exception:
            break

    return todos


def escribir_en_hoja(filas, mes, anio):
    creds_dict = json.loads(GOOGLE_CREDS_RAW)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    cliente = gspread.authorize(creds)

    hoja = cliente.open_by_key(SPREADSHEET_ID).worksheet(HOJA)
    periodo_str = f"{mes:02d}/{anio}"

    # Verificar si el período ya existe para no duplicar
    col_periodo = hoja.col_values(1)
    if periodo_str in col_periodo:
        print(f"El período {periodo_str} ya existe en la hoja, se omite.")
        return

    # Agregar filas al final
    nuevas_filas = [[periodo_str, patente, total] for patente, total in filas]
    hoja.append_rows(nuevas_filas, value_input_option="USER_ENTERED")
    print(f"Se agregaron {len(nuevas_filas)} filas para el período {periodo_str}.")


def enviar_error(error_txt):
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = "ERROR - Consumos mensuales DAZ"
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_DEST
    msg.set_content(
        "Ocurrió un error al procesar los consumos mensuales.\n\n"
        f"Detalle del error:\n{error_txt}"
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


if __name__ == "__main__":
    driver = crear_driver()
    try:
        mes, anio = mes_anterior()
        login(driver)
        _entrar_stock(driver)
        buscar_consumos(driver, mes, anio)
        filas = extraer_todos_los_datos(driver)
        if not filas:
            raise RuntimeError("No se encontraron datos en el reporte.")
        escribir_en_hoja(filas, mes, anio)
    except Exception as e:
        try:
            enviar_error(str(e))
        except Exception:
            pass
        raise
    finally:
        driver.quit()
