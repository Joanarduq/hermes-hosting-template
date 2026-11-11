# Hermes Hosting

Hermes Rclone verifica restauraciones mediante GitHub Actions. El directorio `ia/` añade herramientas de proyecto y un cliente de inferencia. El despliegue requiere un servidor persistente con Docker Compose y disco persistente. Los trabajos programados de GitHub no sirven tráfico de clientes.

## IA privada para el operador

En una máquina dedicada al operador, desde la raíz del repositorio, preparar una sola vez el secreto de cifrado fuera del proyecto:

```bash
umask 077
mkdir -p ~/.config/hermes-ia
( set -C; openssl rand -hex 32 | sed 's/^/ENCRYPTION_KEY=/' > ~/.config/hermes-ia/router.env )
docker compose --env-file ~/.config/hermes-ia/router.env -f ia/compose.yaml up -d --build
curl --fail http://127.0.0.1:3001/api/ping
```

Conservar esa clave junto con una copia protegida del volumen. Abrir el panel desde localhost o un túnel SSH privado, completar el alta del propietario y configurar las credenciales permitidas. Guardar la clave unificada emitida por el router en un archivo privado. El contenedor hereda el healthcheck del proyecto y reinicia tras reiniciar Docker. El ping valida el proceso. Para comprobar inferencia, ejecutar el cliente de abajo en modo personal y con un modelo habilitado en el panel. Verificar persistencia repitiendo la consulta después de recrear el contenedor con el mismo volumen y clave.

## IA de los proyectos contratados

Configurar en el backend de cada proyecto un endpoint compatible con chat completions, un modelo y una clave individual con presupuesto y uso comercial habilitados en el proveedor. Montar el secreto solo en el contenedor de ese proyecto. El cliente se ejecuta dentro de ese backend. Repetir el alta por cliente y establecer los límites en el proveedor. La consola personal está reservada al operador. La configuración de producción usa directamente el endpoint comercial de cada cliente.

```bash
export HERMES_IA_MODO=cliente
export HERMES_IA_URL='https://DOMINIO-DEL-PROVEEDOR/v1'
export HERMES_IA_MODELO='MODELO-HABILITADO'
export HERMES_IA_CLAVE_ARCHIVO='/run/secrets/ia_proyecto'
echo 'Responde con HERMES_OK' | python3 ia/chat.py
```

Para proyectos personales usar `HERMES_IA_MODO=personal` y `HERMES_IA_URL=http://127.0.0.1:3001/v1` desde el host del operador. Configurar el arranque automático del motor Docker en ese servidor. Disponibilidad y cuotas dependen del host y el proveedor.

## Herramientas para los entornos de desarrollo

Ejecutar como el usuario del proyecto con Git, Bash y uv disponibles. Las referencias de origen están fijadas en el lanzador. El primer uso necesita red y espacio para dependencias. Mantener caché, sesiones y archivos separados por cliente.

```bash
bash ia/herramientas.sh reach youtube subtitle 'https://www.youtube.com/watch?v=HTn5Qot690w' --lang es,en
bash ia/herramientas.sh scan /ruta/a/una/skill
bash ia/herramientas.sh ponytail
bash ia/herramientas.sh cine
```

Ponytail imprime la ruta de la guía que se entrega al agente de programación. Cine imprime la guía del checkout completo de Lemo-Opuscar para seleccionar un estilo, instalar sus dependencias y renderizar en el entorno del proyecto. Conservar atribuciones y licencias del material producido. Agent Reach distingue subtítulos de transcripción mediante servicios externos. SkillSpector ejecuta el análisis estático. Revisar sus hallazgos antes de activar componentes de terceros.
