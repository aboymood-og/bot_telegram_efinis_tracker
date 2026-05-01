import telebot
import requests
from bs4 import BeautifulSoup
import time
import threading
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
TOKEN_TELEGRAM = "TU_TOKEN_DE_TELEGRAM_AQUI"
RUT_EFINIS = "tu_rut_aqui"
PASS_EFINIS = "tu_contraseña_aqui"
CHAT_ID_DESTINO = "TU_CHAT_ID" # Necesitamos tu ID para los mensajes automáticos

bot = telebot.TeleBot(TOKEN_TELEGRAM)

URL_LOGIN = "https://efinis.uft.cl/index.php"
URL_CURSOS = "https://efinis.uft.cl/user_portal.php"

# Inicializamos la sesión a nivel GLOBAL para que guarde las cookies entre revisiones
session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 2. FUNCIONES AUXILIARES (CASOS DE USO)
# ==========================================
def rastrear_documento_nuevo(url_carpeta, nombre_curso, session, ruta_actual=""):
    """
    Navega por las carpetas buscando el archivo más reciente (últimos 35 mins).
    Usa recursividad para entrar en subcarpetas.
    """
    # --- EL hack DE LA PAGINACIÓN ---
    # Revisamos si la URL ya tiene el símbolo '?' para saber si añadir un '&' o un '?'
    separador = '&' if '?' in url_carpeta else '?'
    
    # Inyectamos el parámetro brutal que descubriste (le pongo 1000 por si algún profe enloquece subiendo cosas)
    url_optimizada = f"{url_carpeta}{separador}student_table_per_page=1000"
    
    # Hacemos la petición a la carpeta forzando a que muestre todo
    response = session.get(url_optimizada)
    response = session.get(url_carpeta)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Buscamos la tabla de documentos
    tabla = soup.find('table', class_='data_table')
    
    # Caso: Tabla no existe (Sección vacía o bloqueada)
    if not tabla:
        if ruta_actual: # Significa que crearon una carpeta y no le pusieron nada dentro
            return f"📁 *{nombre_curso}*\n   • Se detectó la creación de la carpeta `{ruta_actual}` (actualmente vacía).\n   • [Enlace a la carpeta]({url_carpeta})"
        else: # Oculto en la raíz
            return f"❓ *{nombre_curso}*\n   • Se añadió un archivo pero está oculto por el profesor o hubo un error.\n   • [Enlace a Documentos]({url_carpeta})"
            
    filas = tabla.find_all('tr')[1:] # Ignoramos la primera fila (los encabezados)
    
    elemento_mas_reciente = None
    fecha_maxima = datetime.min
    # Usamos 35 mins de margen para evitar perder algo si el ciclo se retrasa unos segundos
    limite_tiempo = datetime.now() - timedelta(minutes=35) 
    
    # Recorremos cada fila para extraer fechas
    for fila in filas:
        columnas = fila.find_all('td')
        if len(columnas) < 4: continue
        
        # 1. ¿Es carpeta o archivo? (Miramos el ícono en la primera columna)
        es_carpeta = False
        img_tag = columnas[0].find('img')
        if img_tag and 'folder' in img_tag.get('src', ''):
            es_carpeta = True
            
        # 2. Nombre y Link (Segunda columna)
        a_tag = columnas[1].find('a')
        nombre = a_tag.text.strip()
        link = a_tag['href']
        if link.startswith('/'): # Prevenir rutas relativas
            link = "https://efinis.uft.cl" + link
            
        # 3. Extraer la fecha del span oculto (Cuarta columna)
        span_fecha = columnas[3].find('span')
        if span_fecha:
            try:
                # Convertimos el string "2026-04-30 08:48:21" a un objeto de tiempo real
                fecha_obj = datetime.strptime(span_fecha.text.strip(), "%Y-%m-%d %H:%M:%S")
                
                # Vamos guardando siempre el que sea más nuevo
                if fecha_obj > fecha_maxima:
                    fecha_maxima = fecha_obj
                    elemento_mas_reciente = {
                        "nombre": nombre,
                        "link": link,
                        "es_carpeta": es_carpeta,
                        "fecha": fecha_obj
                    }
            except ValueError:
                continue

    # ==========================================
    # LÓGICA DE DECISIÓN BASADA EN LO ENCONTRADO
    # ==========================================
    
    # Si encontramos algo y ese algo fue subido en los últimos 35 minutos
    if elemento_mas_reciente and elemento_mas_reciente['fecha'] >= limite_tiempo:
        
        if elemento_mas_reciente['es_carpeta']:
            # RECURSIVIDAD: Si es carpeta, construimos la ruta y volvemos a llamar a la función
            nueva_ruta = f"{ruta_actual}/{elemento_mas_reciente['nombre']}"
            return rastrear_documento_nuevo(elemento_mas_reciente['link'], nombre_curso, session, nueva_ruta)
            
        else:
            # ES ARCHIVO: Fin de la búsqueda, tenemos a nuestro ganador
            ruta_final = f"{ruta_actual}/{elemento_mas_reciente['nombre']}"
            return f"📄 *{nombre_curso}*\n   • Se añadió un archivo: `{ruta_final}`\n   • [Descargar/Ver archivo]({elemento_mas_reciente['link']})"
            
    else:
        # Nada superó el límite de tiempo. Es el caso de archivos ocultos o carpetas vacías.
        if ruta_actual:
            return f"📁 *{nombre_curso}*\n   • Se detectó una nueva carpeta vacía o con archivos ocultos en: `{ruta_actual}`\n   • [Ver carpeta]({url_carpeta})"
        else:
            return f"❓ *{nombre_curso}*\n   • Se añadió un archivo pero está oculto por el profesor o hubo un error de plataforma.\n   • [Enlace a Documentos]({url_carpeta})"

# Aquí irán después las otras funciones auxiliares:
# def procesar_anuncio(...):
# def procesar_tarea(...):

# ==========================================
# 3. FUNCIÓN DE SCRAPING (OPTIMIZADA)
# ==========================================
def revisar_efinis():
    global session # Usamos la sesión global
    
    try:
        # 1. INTENTAR ACCESO DIRECTO PRIMERO
        response_cursos = session.get(URL_CURSOS, headers=headers)
        
        # Verificamos si realmente estamos en el portal (buscamos algo único de logueado)
        if "Mis cursos" not in response_cursos.text or "Ocurrió un error" in response_cursos.text:
            print("Sesión expirada o no iniciada. Ejecutando Login...")
            
            payload_login = {
                "login": RUT_EFINIS,
                "password": PASS_EFINIS,
                "submitAuth": "",
                "_qf_formLogin": ""
            }
            # Hacer POST para loguearse
            response_login = session.post(URL_LOGIN, data=payload_login, headers=headers)
            
            # Verificar si el login falló
            if "Contraseña incorrecta" in response_login.text:
                return ["Error al iniciar sesión. Revisa credenciales."]
            
            # Si el login fue bien, volvemos a pedir la página de cursos
            response_cursos = session.get(URL_CURSOS, headers=headers)

        # 2. EXTRACCIÓN DE DATOS (Igual que antes)
        soup = BeautifulSoup(response_cursos.text, 'html.parser')
        novedades_encontradas = []
        
        semestre_actual = soup.find('div', class_='panel-group')
        if not semestre_actual:
            return ["No se encontró el bloque del semestre."]

        cursos = semestre_actual.find_all('div', class_='row')

        for curso in cursos:
            titulo_tag = curso.find('h4', class_='course-items-title')
            if not titulo_tag: continue
            
            nombre_curso = titulo_tag.find('a').text.strip()
            iconos_nuevos = titulo_tag.find_all('img', alt=lambda value: value and 'Desde su última visita' in value)
            
            if iconos_nuevos:
                for icono in iconos_nuevos:
                    detalle = icono.get('alt')
                    link = icono.parent.get('href')
                    
                    # Verificamos si el ícono corresponde a la carpeta de documentos
                    if 'folder_document.png' in icono.get('src', ''):
                        mensaje = rastrear_documento_nuevo(link, nombre_curso, session, ruta_actual="Documentos")
                        novedades_encontradas.append(mensaje)
                    else:
                        mensaje_generico = f"🔔 *NOVEDAD EN:* {nombre_curso}\n   • {detalle}\n   • [Enlace directo]({link})"
                        novedades_encontradas.append(mensaje_generico)
                
        return novedades_encontradas

    except Exception as e:
        print(f"Error técnico: {e}")
        return [f"Error técnico: {e}"]

# ==========================================
# 4. BUCLE AUTOMÁTICO (Programado a las :00 y :30)
# ==========================================
def bucle_automatico():
    while True:
        ahora = datetime.now()
        
        # Calculamos cuántos minutos faltan para el próximo :00 o :30
        if ahora.minute < 30:
            minutos_faltantes = 30 - ahora.minute
        else:
            minutos_faltantes = 60 - ahora.minute
            
        # Lo convertimos a segundos y le restamos los segundos actuales para ser 100% exactos
        segundos_a_esperar = (minutos_faltantes * 60) - ahora.second
        
        hora_proxima = ahora.minute + minutos_faltantes
        if hora_proxima == 60: hora_proxima = "00"
        
        print(f"Zzz... El bot dormirá {minutos_faltantes} minutos. Próxima revisión exacta a las XX:{hora_proxima}")
        
        # El bot se pausa exactamente el tiempo necesario
        time.sleep(segundos_a_esperar)
        
        # --- DESPIERTA A LA HORA EN PUNTO ---
        print("⏰ ¡Hora en punto! Ejecutando revisión automática...")
        novedades = revisar_efinis()
        
        if novedades and "Error" not in novedades[0] and "No se encontró" not in novedades[0]:
            for novedad in novedades:
                bot.send_message(CHAT_ID_DESTINO, novedad, parse_mode='Markdown')

# ==========================================
# 5. INTERACCIÓN CON TELEGRAM
# ==========================================
@bot.message_handler(commands=['start', 'ayuda'])
def enviar_bienvenida(message):
    bot.reply_to(message, f"¡Hola! Tu Chat ID es: `{message.chat.id}`. Ponlo en la configuración del script.")

@bot.message_handler(commands=['revisar'])
def comando_revisar(message):
    bot.send_message(message.chat.id, "⏳ Revisando eFinis...")
    novedades = revisar_efinis()
    
    if not novedades:
        bot.send_message(message.chat.id, "✅ Todo limpio.")
    else:
        for novedad in novedades:
            bot.send_message(message.chat.id, novedad, parse_mode='Markdown')

# ==========================================
# 6. ARRANQUE
# ==========================================
if __name__ == '__main__':
    # Arrancamos el hilo automático en segundo plano
    hilo_revision = threading.Thread(target=bucle_automatico)
    hilo_revision.daemon = True # Esto hace que el hilo se cierre si detienes el script
    hilo_revision.start()
    
    print("Bot iniciado y escuchando comandos...")
    bot.infinity_polling()