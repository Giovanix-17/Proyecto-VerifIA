/* VerifIA — lógica de la interfaz (Fase 7).
   Flujo de 4 pasos: entrada → revisión → análisis → resultado.
   Sin frameworks: fetch + manipulación del DOM. */

(() => {
  "use strict";

  const MAXIMO_TEXTO = 10000;

  const NOMBRES_TIPOLOGIA = {
    legitimo: "Mensaje legítimo",
    suplantacion_bancaria: "Probable suplantación bancaria",
    paqueteria_retenida: "Probable paquetería retenida",
    oferta_laboral_fraudulenta: "Probable oferta laboral fraudulenta",
    extorsion: "Probable extorsión",
  };

  /* códigos estables de la API → frases para la persona usuaria */
  const MENSAJES_ERROR = {
    texto_vacio: "Escribe el mensaje que quieres verificar.",
    texto_muy_largo: "El mensaje es demasiado largo (máximo 10 000 caracteres).",
    entrada_invalida: "Revisa los datos enviados.",
    formato_no_soportado: "Solo se admiten imágenes PNG o JPEG.",
    imagen_vacia: "Selecciona una captura PNG o JPEG.",
    imagen_invalida: "La imagen no se pudo leer. Inténtala con otra captura.",
    imagen_demasiado_grande:
      "La imagen es demasiado grande (máximo 5 MB o 4000 px por lado).",
    texto_insuficiente:
      "No se pudo extraer texto suficiente. Usa una captura más nítida o completa.",
    ocr_no_disponible:
      "El lector de texto no está disponible en este momento.",
    demasiadas_solicitudes:
      "Estás enviando mensajes muy rápido. Espera unos segundos.",
    servicio_no_disponible:
      "El servicio no está disponible ahora. Inténtalo más tarde.",
    error_interno: "No se pudo completar el análisis. Inténtalo de nuevo.",
    interfaz_no_disponible: "La interfaz no está disponible.",
    red: "No hay conexión con el servicio. Verifica que esté encendido.",
  };

  const $ = (selector) => document.querySelector(selector);

  const ui = {
    pasos: document.querySelectorAll(".paso"),
    avisos: $("#avisos"),
    secciones: {
      1: $("#paso-1"),
      2: $("#paso-2"),
      3: $("#paso-3"),
      4: $("#paso-4"),
    },
    modoTexto: document.querySelector('input[name="modo"][value="texto"]'),
    mensaje: $("#mensaje"),
    contador: $("#contador"),
    captura: $("#captura"),
    botonPaso1: $("#boton-paso1"),
    explicacionPaso2: $("#paso2-explicacion"),
    revision: $("#texto-revision"),
    avisosOCR: $("#avisos-ocr"),
    botonAnalizar: $("#boton-analizar"),
    botonVolver: $("#boton-volver"),
    veredicto: $("#veredicto"),
    detalle: $("#resultado-detalle"),
    botonOtro: $("#boton-otro"),
  };

  /* ---------------- utilidades ---------------- */

  const escapar = (texto) =>
    String(texto)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

  function mensajeDeError(codigo) {
    return MENSAJES_ERROR[codigo] || MENSAJES_ERROR.error_interno;
  }

  async function llamarAPI(url, opciones) {
    let respuesta;
    try {
      respuesta = await fetch(url, opciones);
    } catch {
      throw { codigo: "red" };
    }
    let cuerpo = {};
    try {
      cuerpo = await respuesta.json();
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    if (!respuesta.ok) {
      throw { codigo: cuerpo.codigo || "error_interno" };
    }
    return cuerpo;
  }

  /* ---------------- navegación por pasos ---------------- */

  function irAPaso(numero) {
    for (const [clave, seccion] of Object.entries(ui.secciones)) {
      seccion.hidden = Number(clave) !== numero;
    }
    ui.pasos.forEach((paso) => {
      const valor = Number(paso.dataset.paso);
      paso.classList.toggle("es-actual", valor === numero);
      paso.classList.toggle("hecho", valor < numero);
      if (valor === numero) {
        paso.setAttribute("aria-current", "step");
      } else {
        paso.removeAttribute("aria-current");
      }
    });
  }

  function avisar(texto) {
    ui.avisos.textContent = texto;
    ui.avisos.hidden = false;
  }

  function limpiarAviso() {
    ui.avisos.hidden = true;
    ui.avisos.textContent = "";
  }

  /* ---------------- paso 1: entrada ---------------- */

  function modoActual() {
    return ui.modoTexto.checked ? "texto" : "imagen";
  }

  function actualizarContador() {
    ui.contador.textContent = String(ui.mensaje.value.length);
  }

  function actualizarVisibilidadModo() {
    const esTexto = modoActual() === "texto";
    $("#panel-texto").hidden = !esTexto;
    $("#panel-imagen").hidden = esTexto;
  }

  async function enviarDesdePaso1() {
    limpiarAviso();
    if (modoActual() === "texto") {
      const texto = ui.mensaje.value;
      if (!texto.trim()) {
        avisar(mensajeDeError("texto_vacio"));
        ui.mensaje.focus();
        return;
      }
      if (texto.length > MAXIMO_TEXTO) {
        avisar(mensajeDeError("texto_muy_largo"));
        ui.mensaje.focus();
        return;
      }
      ui.explicacionPaso2.textContent =
        "Así leeremos tu mensaje. Si quieres cambiar algo, edítalo aquí.";
      ui.avisosOCR.hidden = true;
      ui.revision.value = texto;
      irAPaso(2);
      ui.revision.focus();
      return;
    }

    const archivo = ui.captura.files?.[0];
    if (!archivo) {
      avisar(mensajeDeError("imagen_vacia"));
      ui.captura.focus();
      return;
    }
    if (archivo.type !== "image/png" && archivo.type !== "image/jpeg") {
      avisar(mensajeDeError("formato_no_soportado"));
      ui.captura.focus();
      return;
    }

    ui.botonPaso1.disabled = true;
    ui.botonPaso1.setAttribute("aria-busy", "true");
    ui.botonPaso1.textContent = "Extrayendo texto…";
    try {
      const datos = new FormData();
      datos.append("imagen", archivo, archivo.name);
      const cuerpo = await llamarAPI("/api/analizar/imagen", {
        method: "POST",
        body: datos,
      });
      ui.explicacionPaso2.textContent =
        "Este texto salió de tu captura. Corrige lo que se haya leído mal.";
      ui.revision.value = cuerpo.texto_extraido || "";
      ui.avisosOCR.innerHTML = "";
      const avisos = cuerpo.advertencias || [];
      if (avisos.length) {
        avisos.forEach((texto) => {
          const elemento = document.createElement("li");
          elemento.textContent = texto;
          ui.avisosOCR.appendChild(elemento);
        });
        ui.avisosOCR.hidden = false;
      } else {
        ui.avisosOCR.hidden = true;
      }
      limpiarAviso();
      irAPaso(2);
      ui.revision.focus();
    } catch (error) {
      avisar(mensajeDeError(error.codigo));
    } finally {
      ui.botonPaso1.disabled = false;
      ui.botonPaso1.removeAttribute("aria-busy");
      ui.botonPaso1.textContent = "Analizar mensaje";
    }
  }

  /* ---------------- paso 3 → 4: análisis y resultado ---------------- */

  async function analizar() {
    limpiarAviso();
    const texto = ui.revision.value;
    if (!texto.trim()) {
      avisar(mensajeDeError("texto_vacio"));
      ui.revision.focus();
      return;
    }
    ui.botonAnalizar.disabled = true;
    ui.botonAnalizar.setAttribute("aria-busy", "true");
    irAPaso(3);
    ui.secciones[3].focus(); /* anuncia el estado de espera (aria-live) */
    try {
      const cuerpo = await llamarAPI("/api/analizar/texto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
      });
      /* Primero se muestra el panel y luego se pinta: así la zona
         aria-live anuncia el veredicto y el foco queda en él. */
      irAPaso(4);
      pintarResultado(cuerpo);
      ui.veredicto.focus();
    } catch (error) {
      avisar(mensajeDeError(error.codigo));
      irAPaso(2);
      ui.revision.focus();
    } finally {
      ui.botonAnalizar.disabled = false;
      ui.botonAnalizar.removeAttribute("aria-busy");
    }
  }

  function pintarResultado(r) {
    const clases = {
      verde: "veredicto--verde",
      amarillo: "veredicto--amarillo",
      rojo: "veredicto--rojo",
    };
    ui.veredicto.className = `veredicto ${clases[r.estado] || "veredicto--verde"}`;
    ui.veredicto.innerHTML = `
      <p class="veredicto-encabezado">
        <span class="veredicto-icono" aria-hidden="true">${escapar(r.icono)}</span>
        <span>${escapar(r.titulo)}</span>
      </p>
      <p class="veredicto-tipologia">${escapar(
        NOMBRES_TIPOLOGIA[r.tipologia] || r.tipologia
      )} · puntuación ${Number(r.puntuacion)} de 100</p>
      <p class="veredicto-descripcion">${escapar(r.descripcion)}</p>
      <p class="veredicto-accion"><strong>${escapar(r.accion)}</strong></p>`;

    const partes = [];

    if (r.resumen_legible) {
      partes.push(
        `<div class="bloque"><h3>En pocas palabras</h3><p>${escapar(
          r.resumen_legible
        )}</p></div>`
      );
    }

    if (r.senales_alerta?.length) {
      const items = r.senales_alerta
        .map(
          (senal) => `
        <li>
          <span class="senal-frase">“${escapar(senal.frase)}”</span>
          <span class="senal-motivo">${escapar(senal.motivo)}</span>
        </li>`
        )
        .join("");
      partes.push(
        `<div class="bloque"><h3>Señales de alerta</h3><ul class="senales">${items}</ul></div>`
      );
    }

    if (r.recomendaciones?.length) {
      const items = r.recomendaciones
        .map((rec) => `<li>${escapar(rec)}</li>`)
        .join("");
      partes.push(
        `<div class="bloque"><h3>Lo que puedes hacer</h3><ol class="recomendaciones">${items}</ol></div>`
      );
    }

    if (r.advertencias?.length) {
      const items = r.advertencias
        .map((texto) => `<p class="advertencia">${escapar(texto)}</p>`)
        .join("");
      partes.push(items);
    }

    const resaltado = textoResaltado(r.texto_analizado, r.senales_alerta || []);
    partes.push(`
      <details>
        <summary>Ver el mensaje tal como lo analizamos (datos ya enmascarados)</summary>
        <p class="texto-analizado">${resaltado}</p>
      </details>`);

    if (r.aviso) {
      partes.push(`<p class="aviso-final">${escapar(r.aviso)}</p>`);
    }

    ui.detalle.innerHTML = partes.join("");
  }

  /* Resalta las señales sobre el texto enmascarado usando los offsets que
     entrega la API; si una señal no trae offsets, la busca por su frase. */
  function textoResaltado(texto, senales) {
    const rangos = [];
    senales.forEach((senal) => {
      if (
        Number.isInteger(senal.inicio) &&
        Number.isInteger(senal.fin) &&
        senal.fin > senal.inicio &&
        senal.fin <= texto.length &&
        texto.slice(senal.inicio, senal.fin) === senal.frase
      ) {
        rangos.push([senal.inicio, senal.fin]);
        return;
      }
      const indice = texto.indexOf(senal.frase);
      if (indice !== -1) {
        rangos.push([indice, indice + senal.frase.length]);
      }
    });

    rangos.sort((a, b) => a[0] - b[0]);
    const segmentos = [];
    let cursor = 0;
    for (const [inicio, fin] of rangos) {
      if (inicio < cursor) continue; /* solapado: se conserva el primero */
      segmentos.push(escapar(texto.slice(cursor, inicio)));
      segmentos.push(`<mark>${escapar(texto.slice(inicio, fin))}</mark>`);
      cursor = fin;
    }
    segmentos.push(escapar(texto.slice(cursor)));
    return segmentos.join("");
  }

  /* ---------------- reinicio ---------------- */

  function volverAEmpezar() {
    limpiarAviso();
    ui.revision.value = "";
    ui.avisosOCR.hidden = true;
    ui.avisosOCR.innerHTML = "";
    ui.detalle.innerHTML = "";
    ui.veredicto.className = "veredicto";
    ui.veredicto.innerHTML = "";
    irAPaso(1);
    ui.mensaje.focus();
  }

  /* ---------------- eventos ---------------- */

  document.querySelectorAll('input[name="modo"]').forEach((entrada) => {
    entrada.addEventListener("change", () => {
      limpiarAviso();
      actualizarVisibilidadModo();
    });
  });

  ui.mensaje.addEventListener("input", actualizarContador);
  ui.botonPaso1.addEventListener("click", enviarDesdePaso1);
  ui.botonAnalizar.addEventListener("click", analizar);
  ui.botonVolver.addEventListener("click", volverAEmpezar);
  ui.botonOtro.addEventListener("click", volverAEmpezar);

  actualizarContador();
  actualizarVisibilidadModo();
  irAPaso(1);
})();
