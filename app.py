import streamlit as st
import pymongo
import re
import uuid
import hmac
import logging

from datetime import date
from pymongo import MongoClient

# ====================================
# CONFIGURACION GENERAL
# ====================================

st.set_page_config(
    page_title="EcoGestion",
    page_icon="♻️",
    layout="wide"
)

ESTADOS = [
    "Pendiente",
    "En proceso",
    "Completado",
    "Cancelado"
]

TIPOS_RESIDUO = [
    "Papel y carton",
    "Plastico",
    "Vidrio",
    "Metal",
    "Organicos",
    "Electronicos",
    "Otros"
]

# ====================================
# CREDENCIALES
# ====================================

try:
    MONGODB_URI = st.secrets["app"]["MONGODB_URI"]
    APP_PASSWORD = st.secrets["app"]["APP_PASSWORD"]
except Exception:
    st.error("Faltan las credenciales de la aplicacion.")
    st.stop()

# ====================================
# CONEXION A MONGODB ATLAS
# ====================================

@st.cache_resource
def conectar_mongodb():
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=15000
    )

    client.admin.command("ping")

    db = client["ecogestion_db"]
    return db["servicios_recoleccion"]

# ====================================
# AUTENTICACION
# ====================================

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("EcoGestion - Acceso")

    with st.form("login"):
        password = st.text_input(
            "Contrasena de acceso",
            type="password"
        )
        ingresar = st.form_submit_button("Ingresar")

    if ingresar:
        if hmac.compare_digest(password, APP_PASSWORD):
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Contrasena incorrecta")

    st.stop()

# ====================================
# INICIALIZAR APLICACION
# ====================================

try:
    collection = conectar_mongodb()
except Exception:
    logging.exception("Error conectando con MongoDB")
    st.error("No fue posible conectar con MongoDB Atlas.")
    st.stop()

with st.sidebar:
    st.title("EcoGestion")
    st.write("Sistema de recoleccion de residuos")

    if st.button("Cerrar sesion"):
        st.session_state.autenticado = False
        st.rerun()

st.title("EcoGestion")
st.write(
    "Sistema para registrar, consultar, actualizar "
    "y eliminar servicios de recoleccion de residuos."
)

if "mensaje" in st.session_state:
    st.success(st.session_state.pop("mensaje"))

# ====================================
# PESTANAS CRUD
# ====================================

tab1, tab2, tab3, tab4 = st.tabs([
    "Registrar",
    "Consultar",
    "Actualizar",
    "Eliminar"
])

# ====================================
# CREATE - REGISTRAR
# ====================================

with tab1:
    st.subheader("Registrar nuevo servicio")

    with st.form("form_registro"):

        cliente = st.text_input("Nombre del cliente")
        direccion = st.text_input("Direccion de recoleccion")

        residuo = st.selectbox(
            "Tipo de residuo",
            TIPOS_RESIDUO
        )

        cantidad = st.number_input(
            "Cantidad estimada (kg)",
            min_value=0.1,
            value=10.0
        )

        fecha = st.date_input(
            "Fecha de recoleccion",
            value=date.today()
        )

        observaciones = st.text_area(
            "Observaciones"
        )

        guardar = st.form_submit_button(
            "Registrar servicio"
        )

    if guardar:

        if not cliente.strip() or not direccion.strip():
            st.warning("Completa el cliente y la direccion.")

        else:
            documento = {
                "codigo": "REC-" + uuid.uuid4().hex[:10].upper(),
                "cliente": {
                    "nombre": cliente.strip(),
                    "direccion": direccion.strip()
                },
                "recoleccion": {
                    "residuo": residuo,
                    "cantidad_kg": cantidad,
                    "fecha": fecha.isoformat()
                },
                "estado": "Pendiente",
                "observaciones": observaciones.strip()
            }

            try:
                collection.insert_one(documento)
                st.session_state.mensaje = (
                    "Servicio registrado: " + documento["codigo"]
                )
                st.rerun()

            except Exception:
                logging.exception("Error al registrar")
                st.error("No se pudo registrar el servicio.")

# ====================================
# READ - CONSULTAR
# ====================================

with tab2:
    st.subheader("Consultar servicios")

    buscar = st.text_input(
        "Buscar por nombre del cliente"
    )

    filtro_estado = st.selectbox(
        "Filtrar por estado",
        ["Todos"] + ESTADOS
    )

    filtros = {}

    if buscar.strip():
        filtros["cliente.nombre"] = {
            "$regex": re.escape(buscar.strip()),
            "$options": "i"
        }

    if filtro_estado != "Todos":
        filtros["estado"] = filtro_estado

    try:
        total = collection.count_documents(filtros)

        servicios = list(
            collection.find(filtros)
            .sort("codigo", pymongo.ASCENDING)
            .limit(500)
        )

        st.metric("Servicios encontrados", total)

        datos = []

        for servicio in servicios:
            datos.append({
                "Codigo": servicio["codigo"],
                "Cliente": servicio["cliente"]["nombre"],
                "Residuo": servicio["recoleccion"]["residuo"],
                "Cantidad (kg)": servicio["recoleccion"]["cantidad_kg"],
                "Fecha": servicio["recoleccion"]["fecha"],
                "Estado": servicio["estado"]
            })

        if datos:
            st.dataframe(
                datos,
                use_container_width=True,
                hide_index=True
            )
            if total > 500:
                st.info("Mostrando los primeros 500 servicios.")
        else:
            st.info("No se encontraron servicios.")

    except Exception:
        logging.exception("Error al consultar")
        st.error("No se pudo consultar la informacion.")

# ====================================
# UPDATE - ACTUALIZAR
# ====================================

with tab3:
    st.subheader("Actualizar servicio")

    servicios = list(
        collection.find().sort("codigo", 1)
    )

    if servicios:

        opciones = {
            s["codigo"]: s for s in servicios
        }

        codigo = st.selectbox(
            "Selecciona el servicio",
            list(opciones.keys())
        )

        seleccionado = opciones[codigo]
        clave = str(seleccionado["_id"])

        with st.form("form_actualizar"):

            nuevo_cliente = st.text_input(
                "Nombre del cliente",
                value=seleccionado["cliente"]["nombre"],
                key="cliente_" + clave
            )

            nueva_direccion = st.text_input(
                "Direccion",
                value=seleccionado["cliente"]["direccion"],
                key="direccion_" + clave
            )

            residuo_actual = seleccionado["recoleccion"]["residuo"]

            nuevo_residuo = st.selectbox(
                "Residuo",
                TIPOS_RESIDUO,
                index=(
                    TIPOS_RESIDUO.index(residuo_actual)
                    if residuo_actual in TIPOS_RESIDUO else 0
                ),
                key="residuo_" + clave
            )

            nueva_cantidad = st.number_input(
                "Cantidad (kg)",
                min_value=0.1,
                value=float(
                    seleccionado["recoleccion"]["cantidad_kg"]
                ),
                key="cantidad_" + clave
            )

            nueva_fecha = st.date_input(
                "Fecha",
                value=date.fromisoformat(
                    seleccionado["recoleccion"]["fecha"]
                ),
                key="fecha_" + clave
            )

            nuevo_estado = st.selectbox(
                "Estado",
                ESTADOS,
                index=ESTADOS.index(
                    seleccionado["estado"]
                ),
                key="estado_" + clave
            )

            nuevas_obs = st.text_area(
                "Observaciones",
                value=seleccionado.get("observaciones", ""),
                key="obs_" + clave
            )

            actualizar = st.form_submit_button(
                "Guardar cambios"
            )

        if actualizar:
            if not nuevo_cliente.strip() or not nueva_direccion.strip():
                st.warning("Completa el cliente y la direccion.")
            else:
                try:
                    resultado = collection.update_one(
                        {"_id": seleccionado["_id"]},
                        {
                            "$set": {
                                "cliente.nombre": nuevo_cliente.strip(),
                                "cliente.direccion": nueva_direccion.strip(),
                                "recoleccion.residuo": nuevo_residuo,
                                "recoleccion.cantidad_kg": nueva_cantidad,
                                "recoleccion.fecha": nueva_fecha.isoformat(),
                                "estado": nuevo_estado,
                                "observaciones": nuevas_obs.strip()
                            }
                        }
                    )

                    if resultado.matched_count:
                        st.session_state.mensaje = (
                            "Servicio actualizado correctamente"
                        )
                        st.rerun()
                    else:
                        st.warning("El servicio ya no existe.")

                except Exception:
                    logging.exception("Error al actualizar")
                    st.error("No se pudo actualizar el servicio.")

    else:
        st.info("No hay servicios registrados.")

# ====================================
# DELETE - ELIMINAR
# ====================================

with tab4:
    st.subheader("Eliminar servicio")

    st.warning(
        "Esta operacion eliminara permanentemente el registro."
    )

    servicios = list(
        collection.find().sort("codigo", 1)
    )

    if servicios:

        opciones = {
            s["codigo"]: s for s in servicios
        }

        codigo_eliminar = st.selectbox(
            "Selecciona el servicio a eliminar",
            list(opciones.keys()),
            key="codigo_eliminar"
        )

        servicio_eliminar = opciones[codigo_eliminar]

        st.write(
            "Cliente:",
            servicio_eliminar["cliente"]["nombre"]
        )

        st.write(
            "Estado:",
            servicio_eliminar["estado"]
        )

        with st.form("form_eliminar"):
            confirmar = st.checkbox(
                "Confirmo que deseo eliminar este servicio"
            )

            eliminar = st.form_submit_button(
                "Eliminar servicio"
            )

        if eliminar:

            if not confirmar:
                st.warning("Debes confirmar la eliminacion.")

            else:
                try:
                    resultado = collection.delete_one({
                        "_id": servicio_eliminar["_id"]
                    })

                    if resultado.deleted_count == 1:
                        st.session_state.mensaje = (
                            "Servicio eliminado correctamente"
                        )
                        st.rerun()
                    else:
                        st.warning("El servicio ya no existe.")

                except Exception:
                    logging.exception("Error al eliminar")
                    st.error("No se pudo eliminar el servicio.")

    else:
        st.info("No hay servicios para eliminar.")
