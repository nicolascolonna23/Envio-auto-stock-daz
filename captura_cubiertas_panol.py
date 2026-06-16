# captura_cubiertas_panol.py
# Login menú -> openLink() handoff a Cubiertas -> reporte Stock en Pañol
# -> click "Totales" (AJAX) -> captura del ReportViewer -> Gmail

import os
import time
import smtplib
from email.message import EmailMessage
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =====================================================
# VARIABLES
# =====================================================
USUARIO   = os.environ["CUBIERTAS_USUARIO"]
PASSWORD  = os.environ["CUBIERTAS_PASSWORD"]

GMAIL_USER     = os.environ["GMAIL_USER"]
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASSWORD"]
DESTINATARIO   = os.environ.get("GMAIL_DEST", "nscolonna68@gmail.com")

URL_LOGIN     = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"
URL_CUB_LOGIN = "https://cloud.dazsistemas.com.ar/cubiertas/Login.aspx?empresa=853"
URL_PANOL     = "https://cloud.dazsistemas.com.ar/cubiertas/stock_panol.aspx"

ARCHIVO_PNG = "totales_cubiertas.png"

# =====================================================
# CHROME
# =====================================================
def crear_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1400")
    return webdriver.Chrome(options=options)

# =====================================================
# LOGIN (menú principal)
# =====================================================
def login(driver):
    wait = WebDriverWait(driver, 30)
    driver.get(URL_LOGIN)
    time.sleep(5)
    user = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
    pwd  = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
    driver.execute_script("arguments[0].value='';", user)
    driver.execute_script("arguments[0].value='';", pwd)
    user.send_keys(USUARIO)
    pwd.send_keys(PASSWORD)
    pwd.send_keys(Keys.ENTER)
    time.sleep(8)
    print("URL POST LOGIN:", driver.current_url)

# =====================================================
# HELPERS
# =====================================================
def _entrar_cubiertas(driver):
    """Replica el ícono CUBIERTAS: openLink() autentica el módulo."""
    handles_antes = list(driver.window_handles)
    try:
        driver.execute_script(
            "openLink('W24CUB', '853', '/cubiertas/Login.aspx?empresa=853');"
        )
        time.sleep(7)
    except Exception as ex:
        print("[!] openLink no disponible:", ex)

    nuevas = [h for h in driver.window_handles if h not in handles_antes]
    if nuevas:
        driver.switch_to.window(nuevas[-1])
        time.sleep(3)

    if "/menu/" in driver.current_url.lower():
        driver.get(URL_CUB_LOGIN)
        time.sleep(6)

    print("Entró a CUBIERTAS:", driver.current_url)


def _click_totales(driver):
    """Clickea el elemento cuyo texto es exactamente 'Totales' (prioriza <a>)."""
    def buscar(ctx):
        cands = ctx.find_elements(By.XPATH, "//a | //input | //span | //div | //td")
        for pref in ("a", "input", "span", "div", "td"):
            for e in cands:
                try:
                    if e.tag_name != pref:
                        continue
                    t = (e.text or e.get_attribute("value") or "").strip().lower()
                    if t == "totales":
                        driver.execute_script("arguments[0].click();", e)
                        print("Click en 'Totales' (tag:", pref, ")")
                        return True
                except Exception:
                    pass
        return False

    if buscar(driver):
        return True
    # por si el reporte está dentro de un iframe
    for fr in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(fr)
            if buscar(driver):
                driver.switch_to.default_content()
                return True
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
    return False

# =====================================================
# CAPTURAR TOTALES
# =====================================================
def capturar_totales(driver):
    # 1) Autenticar el módulo Cubiertas
    _entrar_cubiertas(driver)

    # 2) Ir al reporte de stock en pañol
    driver.get(URL_PANOL)
    time.sleep(12)  # el ReportViewer tarda en renderizar
    print("URL reporte:", driver.current_url)
    if "login" in driver.current_url.lower():
        print("[!] OJO: terminó en login del módulo.")

    # 3) Click en "Totales" (dispara la recarga AJAX hacia el resumen)
    if _click_totales(driver):
        time.sleep(10)  # esperar que cargue la vista de totales
    else:
        print("[!] No se encontró 'Totales'. Capturo el reporte como está.")
        time.sleep(3)

    # 4) Capturar el ReportViewer (es un <span>, no un div)
    selectores = [
        "span[id*='rvReporte_ReportViewer']",
        "[id*='rvReporte_ReportViewer']",
        "[id*='ReportViewer']",
        "[id*='oReportDiv']",
        "div.contenido",
    ]
    elemento = None
    for sel in selectores:
        try:
            elemento = driver.find_element(By.CSS_SELECTOR, sel)
            print("Capturando elemento:", sel)
            break
        except Exception:
            pass

    try:
        if elemento is not None:
            elemento.screenshot(ARCHIVO_PNG)
        else:
            print("[!] No se ubicó el ReportViewer, capturo pantalla completa.")
            driver.save_screenshot(ARCHIVO_PNG)
        print("Captura guardada:", ARCHIVO_PNG)
    except Exception as ex:
        print("[!] Fallo la captura del elemento, capturo pantalla completa:", ex)
        driver.save_screenshot(ARCHIVO_PNG)

    return ARCHIVO_PNG

# =====================================================
# ENVIAR POR GMAIL
# =====================================================
def enviar_gmail(ruta_png):
    msg = EmailMessage()
    hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    msg["Subject"] = f"Totales Cubiertas en pañol - {hoy}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = DESTINATARIO
    msg.set_content(f"Captura automática de Totales (Cubiertas en pañol) generada el {hoy}.")

    with open(ruta_png, "rb") as f:
        msg.add_attachment(f.read(), maintype="image", subtype="png",
                           filename=os.path.basename(ruta_png))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        smtp.send_message(msg)
    print("Correo enviado a:", DESTINATARIO)

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    driver = crear_driver()
    try:
        login(driver)
        png = capturar_totales(driver)
        enviar_gmail(png)
    finally:
        driver.quit()
