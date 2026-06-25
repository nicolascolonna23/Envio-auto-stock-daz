import os
import time
import smtplib
from email.message import EmailMessage

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL_LOGIN = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_PANOL = "https://cloud.dazsistemas.com.ar/cubiertas/stock_panol.aspx"

USUARIO = os.environ["CUBIERTAS_USUARIO"]
PASSWORD = os.environ["CUBIERTAS_PASSWORD"]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
GMAIL_DEST = os.environ["GMAIL_DEST"]

TOTALES_PNG = "totales_cubiertas.png"

SELECTORES_REPORTE = [
    "span[id*='rvReporte_ReportViewer']",
    "div[id*='ReportViewer']",
    "div[id*='rvReporte']",
    "iframe[id*='ReportFrame']",
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


def _entrar_cubiertas(driver):
    wait = WebDriverWait(driver, 20)
    wait.until(lambda d: d.execute_script("return typeof openLink === 'function';"))
    ventanas_antes = set(driver.window_handles)
    driver.execute_script("openLink('W24CUB', '853', '/cubiertas/Login.aspx?empresa=853');")
    time.sleep(3)

    ventanas_despues = set(driver.window_handles)
    nuevas = ventanas_despues - ventanas_antes
    if nuevas:
        driver.switch_to.window(nuevas.pop())

    wait.until(EC.url_contains("/cubiertas/"))
    time.sleep(2)


def _capturar_reporte(driver, ruta_png):
    alto_total = driver.execute_script(
        "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
    )
    driver.set_window_size(1920, alto_total + 200)
    time.sleep(1)
    driver.save_screenshot(ruta_png)
    driver.set_window_size(1920, 1400)


def _boton_siguiente_pagina(driver):
    candidatos = driver.find_elements(
        By.XPATH,
        "//input[@title='Next Page'] | //input[@title='Página siguiente'] | "
        "//a[@title='Next Page'] | //a[@title='Página siguiente'] | "
        "//input[contains(@class,'rvNextPage')] | //a[contains(@class,'rvNextPage')]",
    )
    for btn in candidatos:
        if btn.is_displayed() and btn.is_enabled():
            return btn
    return None


def _esta_deshabilitado(boton):
    disabled = boton.get_attribute("disabled")
    clase = boton.get_attribute("class") or ""
    if disabled:
        return True
    if "disabled" in clase.lower():
        return True
    return False


def capturar_todas_las_paginas_listado(driver):
    rutas = []
    numero_pagina = 1

    while True:
        ruta = f"listado_cubiertas_pagina_{numero_pagina}.png"
        _capturar_reporte(driver, ruta)
        rutas.append(ruta)
        print(f"Capturada página {numero_pagina}: {ruta}")

        boton = _boton_siguiente_pagina(driver)
        if boton is None or _esta_deshabilitado(boton):
            break

        boton.click()
        time.sleep(3)
        numero_pagina += 1

    return rutas


def _buscar_boton_totales(driver):
    driver.switch_to.default_content()
    xpath = (
        "//a[normalize-space()='Totales'] | //input[@value='Totales'] | "
        "//button[normalize-space()='Totales'] | "
        "//input[@type='button' and @value='Totales'] | "
        "//input[@type='submit' and @value='Totales'] | "
        "//span[normalize-space()='Totales'] | //div[normalize-space()='Totales'] | "
        "//td[normalize-space()='Totales']"
    )
    candidatos = driver.find_elements(By.XPATH, xpath)
    if candidatos:
        return candidatos[0]

    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(iframe)
            candidatos = driver.find_elements(By.XPATH, xpath)
            if candidatos:
                return candidatos[0]
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return None


def _click_totales(driver):
    # Recargar la página para estar en página 1 con el botón Totales visible
    driver.get(URL_PANOL)
    wait = WebDriverWait(driver, 30)
    wait.until(lambda d: any(
        d.find_elements(By.CSS_SELECTOR, selector) for selector in SELECTORES_REPORTE
    ))
    time.sleep(3)
    boton = wait.until(lambda d: _buscar_boton_totales(d))
    boton.click()
    time.sleep(3)


def capturar_cubiertas_panol(driver):
    _entrar_cubiertas(driver)
    driver.get(URL_PANOL)

    wait = WebDriverWait(driver, 30)
    wait.until(lambda d: any(
        d.find_elements(By.CSS_SELECTOR, selector) for selector in SELECTORES_REPORTE
    ))
    time.sleep(2)

    rutas_listado = capturar_todas_las_paginas_listado(driver)

    _click_totales(driver)
    _capturar_reporte(driver, TOTALES_PNG)

    return rutas_listado


def enviar_gmail(rutas_listado):
    todas = rutas_listado + [TOTALES_PNG]

    msg = EmailMessage()
    msg["Subject"] = "Reporte semanal - Cubiertas en pañol"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_DEST

    paginas = len(rutas_listado)
    msg.set_content(
        f"Se adjuntan el listado completo ({paginas} página{'s' if paginas > 1 else ''}) "
        "y el resumen de totales de cubiertas en pañol."
    )

    for ruta in todas:
        with open(ruta, "rb") as f:
            datos = f.read()
        msg.add_attachment(datos, maintype="image", subtype="png", filename=os.path.basename(ruta))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


def enviar_error(error_txt):
    msg = EmailMessage()
    msg["Subject"] = "ERROR - Reporte de cubiertas en pañol"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_DEST
    msg.set_content(
        "Ocurrió un error al generar el reporte de cubiertas en pañol.\n\n"
        f"Detalle del error:\n{error_txt}"
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)


if __name__ == "__main__":
    driver = crear_driver()
    try:
        login(driver)
        rutas_listado = capturar_cubiertas_panol(driver)
        enviar_gmail(rutas_listado)
    except Exception as e:
        try:
            enviar_error(str(e))
        except Exception:
            pass
        raise
    finally:
        driver.quit()
