# osu! Beatmap Recommender

Recomendador de mapas para **osu!standard** (Windows). Analiza tus mejores plays y lo que estás jugando hoy y te propone mapas con dos objetivos:

- **PP:** mapas que te den pp según tu nivel, para farmear.
- **Skillcap:** mapas cerca de tu techo de dificultad, elegidos según las skills que juegas ahora.

Soporta mods **NM, HD, HR y DT** (y sus combinaciones), muestra con qué mods jugar cada mapa y tiene un botón para abrirlo en osu!direct.

> Guía completa de la interfaz: [docs/guia-de-usuario.md](docs/guia-de-usuario.md)

## Requisitos

- Windows 10 u 11.
- **Python 3.10 o superior** (probado con 3.14). Durante la instalación de Python marca **«Add python.exe to PATH»**.
- Una cuenta de osu! y una **aplicación OAuth** propia (ver paso 3).
- Conexión a internet. La primera instalación descarga varios cientos de MB (PySide6).

## Instalación paso a paso

1. **Descarga el proyecto** y descomprímelo en una carpeta fija (por ejemplo `C:\osu-recommender`). Con git:

   ```bat
   git clone https://github.com/maxigarciadelpino/osu-Beatmap-Recommender.git
   ```

2. **Instala las dependencias:** haz doble clic en `dependencies.bat`. Instala `requests`, `python-dotenv`, `rosu-pp-py`, `pillow`, `PySide6` y `customtkinter`, comprueba que todo importe y ofrece crear un acceso directo en el escritorio. Debe terminar con «Todo OK».

3. **Crea tu aplicación OAuth** en osu!:
   1. Entra a <https://osu.ppy.sh/home/account/edit#oauth>.
   2. Pulsa **New OAuth Application**, ponle cualquier nombre y deja vacía la URL de callback.
   3. Copia el **Client ID** y el **Client Secret** (trátalo como una contraseña).

4. **Abre el programa** con `o!br.vbs` (sin terminal) o con el acceso directo del escritorio. En la pantalla de inicio escribe tu usuario de osu!, el Client ID y el Client Secret, deja marcado «Recordarme» y pulsa **Iniciar sesión**. La primera vez construye tu perfil y puede tardar unos minutos.

A partir de ahí, el programa inicia sesión solo al abrirse (mantén **Shift** pulsado al abrirlo para evitarlo).

### Instalación manual (terminal)

```bat
python -m pip install -r requirements.txt
python app.py
```

Ejecutar con `python app.py` muestra los mensajes en la terminal, lo que ayuda si algo falla.

### Acceso directo en el escritorio

Haz doble clic en `create_DA.vbs`. Crea «osu! Recommender» en tu escritorio (aunque esté en OneDrive) y muestra dónde quedó.

## Qué hace cada archivo

| Archivo / carpeta | Función |
|---|---|
| `app.py` | Punto de entrada. Abre la interfaz Qt (PySide6); si PySide6 no está instalado, abre la interfaz anterior (CustomTkinter). |
| `dependencies.bat` | Instala y verifica las dependencias. |
| `o!br.vbs` | Abre el programa sin consola. |
| `create_DA.vbs` | Crea el acceso directo en el escritorio. |
| `cli.py` | Versión de consola (ver abajo). |
| `requirements.txt` | Lista de paquetes de Python. |
| `osu_rec/` | Código: acceso a la API, perfil, recomendador, sesión, patrones y las dos interfaces (`qt/` y `ui/`). |
| `assets/` | Iconos. |
| `data/` | Se crea sola: perfil, cachés, mapas y miniaturas descargados, credenciales guardadas. **No se sube a git.** |
| `docs/` | Documentación. |
| `LICENSE` | Licencia MIT. |

## Uso por consola (opcional)

```bat
python cli.py fetch                      :: descarga tus best scores
python cli.py profile                    :: construye tu perfil
python cli.py recommend pp --mods NM,HD --results 10
python cli.py recommend skillcap --mods DT --all
```

Opciones de `recommend`: `--style`, `--mods` (`NM,HD,HR,DT`), `--sort`, `--maps`, `--results`, `--all`, `--pp-low`, `--pp-high`, `--no-session`, `--require-refs`. El nombre de usuario sale de `data/credentials.env`; con `--user "Nombre"` (antes del comando) puedes indicar otro.

## Seguridad

- Con «Recordarme», tus credenciales se guardan **en texto plano** en `data/credentials.env`. Ese archivo está excluido por `.gitignore`: **nunca lo subas**.
- Si publicaste tu Client Secret por accidente, genera uno nuevo en la página de OAuth de osu!.
- «Cerrar sesión y olvidar credenciales» (menú de tu foto de perfil) borra el archivo.

## Problemas frecuentes

| Problema | Solución |
|---|---|
| `dependencies.bat` dice que no encuentra Python | Instala Python y marca «Add python.exe to PATH». |
| Falla al instalar `rosu-pp-py` o `PySide6` | Prueba con Python 3.12 o 3.13. |
| El programa corre pero no se ve la ventana | Usa la versión actual de `o!br.vbs` o ejecuta `python app.py`; revisa `debug.log`. |
| No abre y no hay mensaje | Revisa `error.log` y `debug.log` en la carpeta del proyecto. |
| «Credenciales inválidas o sin conexión» | Revisa Client ID, Secret y tu conexión. |
| Quiero volver a la interfaz anterior | `python -m pip uninstall PySide6`. |

Más soluciones y la explicación de cada pantalla están en la [guía de usuario](docs/guia-de-usuario.md).

## Cómo funciona (resumen)

El programa descarga tu top 100 con la API v2 de osu!, calcula dificultad y pp de cada mapa en tu PC con [`rosu-pp`](https://github.com/MaxOhn/rosu-pp-py), y busca mapas ranked parecidos a los que mejor juegas. Respeta el límite de la API (alrededor de 1 petición por segundo). Detalles de cada cálculo: sección 7 de la guía.

## Licencia y créditos

Este proyecto se distribuye bajo la [licencia MIT](LICENSE). Puedes usarlo, copiarlo, modificarlo y distribuirlo, incluso en proyectos propios o comerciales, siempre que **conserves el aviso de copyright y el texto de la licencia**, es decir, que mantengas el crédito a su autor: [maxigarciadelpino](https://github.com/maxigarciadelpino).

Las dependencias (rosu-pp-py, PySide6, etc.) tienen sus propias licencias.

Proyecto no oficial: no está afiliado a osu! ni a ppy Pty Ltd.
