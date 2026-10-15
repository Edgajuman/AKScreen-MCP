# AK Screen MCP

Controla **AK Screen** desde Claude Desktop, Claude Code, Codex u otro cliente MCP
compatible con stdio. El agente usa los comandos reales del editor: clips,
efectos, texto, subtítulos, cámara, gráficos, fotogramas clave, audio y exportación.

**Compatible con AK Screen 3.0 y versiones posteriores.**

[**Descargar AK Screen**](https://github.com/Edgajuman/AKScreen-Downloads/releases)
· [Repositorio de descargas](https://github.com/Edgajuman/AKScreen-Downloads)
· [Skill complementaria](https://github.com/Edgajuman/AKScreen-Skill)

Instala AK Screen 3.0 o posterior y conecta el MCP al ejecutable de esa versión.

## Instalación

Necesitas Python 3.10 o posterior. Con [uv](https://docs.astral.sh/uv/):

```sh
uvx --from git+https://github.com/Edgajuman/AKScreen-MCP ak-screen-mcp --launch "C:/ruta/a/AKScreen.exe"
```

También puedes clonar el repositorio y ejecutar `python -m pip install .`.
No hay dependencias de ejecución ni cuenta online para controlar el editor.

## Claude Desktop y otros clientes stdio

Añade esta entrada a la configuración MCP de tu cliente, sustituyendo la ruta:

```json
{
  "mcpServers": {
    "ak-screen": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/Edgajuman/AKScreen-MCP",
        "ak-screen-mcp", "--launch", "C:/ruta/a/AKScreen.exe"
      ]
    }
  }
}
```

El modo `--launch` inicia una sesión del editor con una clave aleatoria en memoria.
El editor no se cierra al desconectar al agente: tu trabajo sin guardar se conserva.
Para otra instancia usa `--port 9877` en la configuración de ese servidor.

Si prefieres iniciar el editor tú mismo, define `AKSCREEN_CONTROL_TOKEN` (32–256
caracteres ASCII imprimibles sin espacios) para **ambos procesos**, ejecuta `AKScreen.exe --control 9876`, y
después `ak-screen-mcp --port 9876`. No publiques esa clave ni la compartas con
servicios externos. La conexión se limita a `127.0.0.1`.

## Skill complementaria

Instala [AK Screen Editing](https://github.com/Edgajuman/AKScreen-Skill).
El MCP proporciona herramientas; la skill explica cómo editar con ellas,
descubrir comandos, verificar el resultado y conservar el proyecto original.

Ejemplos de peticiones:

- «Abre mi proyecto, aplica una corrección suave al segundo clip y muéstrame el resultado».
- «Crea un rótulo con mi fuente local y anima su entrada durante un segundo».
- «Aplica un movimiento de cámara y añade un gráfico de barras con estos datos».
- «Recorta las pausas que te indiqué y exporta una copia MP4 a esta carpeta».

## Herramientas

| Herramienta | Función |
|---|---|
| `command_list` | IDs, parámetros y disponibilidad del editor abierto |
| `doc_inspect` | Proyecto, secuencia e identificadores actuales |
| `command_run` | Ejecutar un comando del editor |
| `command_batch` | Hasta 50 comandos secuenciales; para al primer error |
| `ui_inspect`, `ui_elements` | Consultar controles y sus IDs |
| `ui_control` | Operar controles del propio editor |
| `render_preview` | Imagen del monitor Program o de un panel solicitado |
| `undo` | Deshacer una operación |

Cada edición utiliza el historial del editor. Un lote no es una transacción:
puede haber cambios aplicados antes de un error. Una operación cuyo resultado
se perdió por desconexión **no se reintenta automáticamente**.

Las exportaciones se envían como trabajos en segundo plano. Consulta `jobs.list`
mediante `command_run` para conocer su estado, sin iniciar otra exportación.

## Desarrollo

```sh
python -m pip install -e .
python -m unittest discover -s tests
```

Las pruebas verifican protocolo stdio, autenticación local, límites, lotes,
desconexiones y recuperación de errores frente a un editor de prueba.

MIT · @edgajuman. El canal de comandos proviene de la arquitectura abierta de
[FilmCraft](https://github.com/storytold/filmcraft); el puente, la autenticación
y esta distribución de AK Screen se mantienen aquí.
