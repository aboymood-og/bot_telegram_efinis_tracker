# 🤖 eFinis Tracker Bot

Un bot de Telegram automatizado diseñado para monitorear la plataforma eFinis de la Universidad Finis Terrae. El bot revisa la plataforma silenciosamente en segundo plano y te notifica cada 15 minutos sobre nuevas tareas, anuncios y documentos subidos por los profesores, en el caso de que halla una novedad.

## ✨ ¿Qué hace?
* **Monitoreo Automático:** Revisa la plataforma automáticamente cada 15 minutos exactos (00, 15, 30, 45).
* **Notificaciones de Tareas (Lápiz):** Detecta nuevas tareas subidas, extrae las instrucciones y calcula el tiempo restante. También incluye recordatorios de tareas urgentes (menos de 48 hrs).
* **Notificaciones de Anuncios (Campana):** Intercepta la API de Chamilo para leer el contenido de los anuncios nuevos sin marcarlos como leídos en tu cuenta.
* **Rastreo de Documentos (Carpeta):** Navega recursivamente por las carpetas del curso buscando archivos subidos en los últimos minutos.
* **Keep-Alive:** Mantiene la sesión del servidor activa haciendo peticiones cada 15 minutos, evitando re-logueos constantes que saturen los servidores de la universidad.
* **Modo Sueño (Sleep Mode):** Entra en hibernación automáticamente desde las 00:00 hasta las 08:00 AM para ahorrar recursos, ya que es improbable que se suba material en ese horario.
* **Alerta de Credenciales:** Sistema de seguridad que te avisa por Telegram si tu contraseña del portal ha expirado o fue cambiada.
* **Peticiones Manuales:** Permite consultar el estado de la plataforma en cualquier momento usando el comando `/revisar` en Telegram.

---

## ⚙️ ¿Cómo funciona técnicamente?
El bot está construido en Python. Utiliza la librería `requests` para manejar sesiones web y cookies, imitando el comportamiento de un navegador real. Usa `BeautifulSoup4` para hacer *web scraping* del panel de inicio y leer los iconos de alerta (Desde su última visita).

Para los Anuncios y Tareas, hace ingeniería inversa a las peticiones AJAX (jqGrid) del servidor de Chamilo, extrayendo los datos puros en formato JSON antes de que se rendericen en la página, lo que permite una mayor precisión y velocidad. La arquitectura usa `threading` (hilos) para separar el bucle automático de la escucha de comandos de Telegram, permitiendo que ambos funcionen de forma concurrente.

---

## 🚀 Guía de Instalación y Uso

### Paso 1: Crear el Bot en Telegram
1. Abre Telegram y busca al usuario **@BotFather**.
2. Envíale el comando `/newbot`.
3. Elige un nombre para tu bot (ej. `eFinis Tracker`).
4. Elige un *username* que termine en bot (ej. `efinis_bot`).
5. BotFather te dará un **Token HTTP API** (una cadena larga de letras y números). Cópialo y guárdalo, lo necesitarás en el código.

### Paso 2: Preparar el Entorno (Linux Mint / Ubuntu)
Abre tu terminal e instala las dependencias necesarias de Python:
```bash
pip3 install pyTelegramBotAPI beautifulsoup4 requests
```

### Paso 3: Obtener tu Chat ID y Configurar el Código

1. Abre el archivo bot_efinis_github.py (o como lo hayas nombrado) con tu editor de texto.

2. Pega el Token de BotFather en la variable TOKEN_TELEGRAM.

3. Pon tu RUT (sin puntos ni guion) en RUT_EFINIS y tu clave en PASS_EFINIS.

4. Ejecuta el bot temporalmente en tu terminal: python3 bot_efinis_github.py

5. Ve a Telegram, busca tu bot recién creado y mándale el comando /start.

6. El bot te responderá con tu Chat ID (un número largo).

7. Detén el bot en la terminal (Ctrl + C), pega ese número en la variable CHAT_ID_DESTINO del código y guarda el archivo.


## ⚠️ Aviso Legal

Este script fue creado con fines estrictamente educativos y personales para optimizar la gestión del tiempo de estudio. No realiza peticiones masivas y respeta los tiempos de sesión (Keep-Alive) para no sobrecargar la infraestructura de la Universidad. Nunca compartas tu archivo .py públicamente en GitHub sin antes borrar tu RUT, Contraseña y Token de Telegram.
