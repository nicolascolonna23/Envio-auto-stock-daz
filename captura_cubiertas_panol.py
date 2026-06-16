# captura_cubiertas_panol.py
# Login menú -> CLICK ícono CUBIERTAS (autentica el módulo) ->
# CLICK "Cubiertas en pañol" -> botón "Totales" -> captura ReportViewer -> Gmail

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

URL_LOGIN = "https://cloud.dazsistemas.com.ar/menu/Login.aspx"

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
# HELPERS DE NAVEGACIÓN
# =====================================================
def _entrar_cubiertas(driver):
    """Click en el ícono CUBIERTAS del menú (autentica el sub-sistema)."""
    handles_antes = driver.window_handles
    target = None
    for a in driver.find_elements(By.XPATH, "//a"):
        try:
            href = (a.get_attribute("href") or "").lower()
            txt  = (a.text or "").strip().lower()
            if "cubiertas" in href or txt == "cubiertas":
                target = a
                break
        except Exception:
            pass
    if target is None:
        print("[!] No se encontró el ícono CUBIERTAS en el menú.")
        return False
    driver.execute_script("arguments[0].click();", target)
    time.sleep(7)
    # si abrió en una ventana/pestaña nueva, cambiar a ella
    if len(driver.window_handles) > len(handles_antes):
        driver.switch_to.window(driver.window_handles[-1])
    print("Entró a CUBIERTAS:", driver.current_url)
    return True


def _click_por_texto(driver, palabras, descripcion):
    """Clickea el primer elemento cuyo texto o href contenga alguna palabra."""
    elementos = driver.find_elements(
        By.XPATH,
        "//a | //input[@type='button'] | //input[@type='submit'] | //span | //td | //div"
    )
    for e in elementos:
        try:
            txt  = (e.text or e.get_attribute("value") or "").strip().lower()
            href = (e.get_attribute("href") or "").lower()
            if any(p in txt for p in palabras) or any(p in href for p in palabras):
                driver.execute_script("arguments[0].click();", e)
                print(f"Click {descripcion}: {txt or href}")
                return True
        except Exception:
            pass
    return False


def _buscar_totales(driver):
    for e in driver.find_elements(
        By.XPATH,
        "//a | //button | //span | //td | //input[@type='button'] | //input[@type='submit']"
    ):
        try:
            txt = (e.text or e.get_attribute("value") or "").strip().lower()
            if txt == "totales" or ("total" in txt and len(txt) < 15):
                driver.execute_script("arguments[0].click();", e)
                print("Click en 'Totales':", txt)
                return True
        except Exception:
            pass
    return False

# =====================================================
# CAPTURAR TOTALES
# =====================================================
def capturar_totales(driver):
    # 1) Autenticar el módulo Cubiertas haciendo CLICK en el ícono
    if not _entrar_cubiertas(driver):
        driver.save_screenshot(ARCHIVO_PNG)
        return ARCHIVO_PNG

    # 2) Ir a "Cubiertas en pañol" clickeando el link del menú
    time.sleep(3)
    clic = _click_por_texto(driver, ["panol", "pañol"], "Cubiertas en pañol")
    if not clic:
        print("[!] No se encontró 'Cubiertas en pañol'. Intento URL directa (ya con sesión).")
        driver.get("https://cloud.dazsistemas.com.ar/cubiertas/stock_panol.aspx")

    time.sleep(12)  # el ReportViewer tarda en renderizar
    print("URL reporte:", driver.current_url)
    if "login" in driver.current_url.lower():
        print("[!] OJO: terminó en el login del módulo. La sesión no se autenticó.")

    # 3) Click en "Totales" (página y, si no, dentro de iframes)
    clickeado = _buscar_totales(driver)
    if not clickeado:
        for fr in driver.find_elements(By.TAG_NAME, "iframe"):
            try:
                driver.switch_to.frame(fr)
                if _buscar_totales(driver):
                    clickeado = True
                    driver.switch_to.default_content()
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()
    if not clickeado:
        print("[!] No se encontró 'Totales'. Capturo el reporte igual.")

    time.sleep(8)

    # 4) Capturar el área del ReportViewer
    selectores = [
        (By.CSS_SELECTOR, "div[id*='ReportViewer']"),
        (By.CSS_SELECTOR, "table[id*='ReportViewer']"),
        (By.CSS_SELECTOR, "div[id*='VisibleReportContent']"),
    ]
    elemento = None
    for by, sel in selectores:
        try:
            elemento = driver.find_element(by, sel)
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
