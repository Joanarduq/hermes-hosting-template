"""Cliente de proyecto. Lee el mensaje de stdin y un secreto del propio hosting."""
import json
import os
from pathlib import Path
import sys
from urllib import error, parse, request


class SinRedireccion(request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def consultar(mensaje):
    modo = os.environ["HERMES_IA_MODO"]
    if modo not in ("personal", "cliente"):
        raise ValueError("modo")
    base = os.environ.get("HERMES_IA_URL", "http://127.0.0.1:3001/v1" if modo == "personal" else "")
    url = parse.urlsplit(base)
    local = modo == "personal" and url.hostname in ("localhost", "127.0.0.1", "::1")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("URL")
    if url.scheme != "https" and not (local and url.scheme == "http"):
        raise ValueError("transporte")
    modelo = os.environ["HERMES_IA_MODELO"].strip()
    clave = Path(os.environ["HERMES_IA_CLAVE_ARCHIVO"]).read_text().strip()
    if not all((modelo, clave, mensaje.strip())):
        raise ValueError("faltan datos")
    datos = {"model": modelo, "messages": [{"role": "user", "content": mensaje}]}
    req = request.Request(base.rstrip("/") + "/chat/completions", json.dumps(datos).encode(),
                          {"Authorization": "Bearer " + clave, "Content-Type": "application/json"})
    with request.build_opener(SinRedireccion()).open(req, timeout=90) as respuesta:
        contenido = json.load(respuesta)["choices"][0]["message"]["content"]
    if not isinstance(contenido, str) or not contenido.strip():
        raise ValueError("respuesta sin texto")
    return contenido


if __name__ == "__main__":
    try:
        print(consultar(sys.stdin.read()))
    except error.HTTPError as exc:
        sys.exit(f"El proveedor respondió HTTP {exc.code}.")
    except (ValueError, KeyError, IndexError, TypeError, OSError):
        sys.exit("No se completó la consulta. Comprueba configuración, secreto, conectividad y modelo.")
