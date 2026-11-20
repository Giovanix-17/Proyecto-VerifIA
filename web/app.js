/* VerifIA — lógica de la interfaz (Fase 7, mejoras).
   Flujo de 4 pasos: entrada → revisión → análisis → resultado.
   Sin frameworks: fetch + manipulación del DOM. */

(() => {
  "use strict";

  const MAXIMO_TEXTO = 10000;
  const LIMITE_IMAGEN_BYTES = 5 * 1024 * 1024;
  const LADO_MAXIMO = 4000;

  const NOMBRES_TIPOLOGIA = {
    legitimo: "Mensaje legítimo",
    suplantacion_bancaria: "Probable suplantación bancaria",
    paqueteria_retenida: "Probable paquetería retenida",
    oferta_laboral_fraudulenta: "Probable oferta laboral fraudulenta",
    extorsion: "Probable extorsión",
  };

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
    modoImagen: document.querySelector('input[name="modo"][value="imagen"]'),
    mensaje: $("#mensaje"),
    contador: $("#contador"),
    captura: $("#captura"),
    zonaLanzamiento: $("#zona-lanzamiento"),
    botonElegirArchivo: $("#zona-lanzamiento .dropzone-boton"),
    vistaPrevia: $("#vista-previa"),
    imagenVistaPrevia: $("#imagen-vista-previa"),
    nombreArchivo: $("#nombre-archivo"),
    quitarVista: $("#quitar-vista"),
    errorDropzone: $("#error-dropzone"),
    botonPaso1: $("#boton-paso1"),
    explicacionPaso2: $("#paso2-explicacion"),
    revision: $("#texto-revision"),
    avisosOCR: $("#avisos-ocr"),
    botonAnalizar: $("#boton-analizar"),
    botonVolverPaso2: $("#boton-atras-paso2"),
    veredicto: $("#veredicto"),
    detalle: $("#resultado-detalle"),
    botonAtrasPaso4: $("#boton-atras-paso4"),
    botonCopiar: $("#boton-copiar"),
    botonOtro: $("#boton-otro"),
    esperaTexto: $(".espera-texto"),
    esperaTiempo: $(".espera-tiempo"),
    botonCancelar: $("#boton-cancelar"),
    paso2: $("#paso-2"),
    paso4: $("#paso-4"),
  };

  /* ---------------- estado ---------------- */

  let archivoSeleccionado = null;
  let controladorAborto = null;
  let inicioEspera = null;
  let temporizador = null;
  let historialPasos = [1]; /* pila para el botón Atrás */

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

  function mostrarToast(texto) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = texto;
    document.body.appendChild(toast);
    /* fuerza reflow para que la transición de opacidad funcione */
    toast.offsetHeight;
    toast.classList.add("visible");
    setTimeout(() => {
      toast.classList.remove("visible");
      setTimeout(() => toast.remove(), 220);
    }, 1800);
  }

  /* ---------------- historial y navegación ------------ */

  function entrarHistorial(numero) {
    historialPasos.push(numero);
    history.pushState({ paso: numero }, "", `#paso-${numero}`);
    actualizarRiel(numero);
  }

  function manejarRetroceso() {
    if (historialPasos.length <= 1) return;
    historialPasos.pop();
    const anterior = historialPasos[historialPasos.length - 1];
    irAPaso(anterior, { historial: false });
  }

  function irAPaso(numero, { historial = true } = {}) {
    if (historial) entrarHistorial(numero);

    for (const [clave, seccion] of Object.entries(ui.secciones)) {
      seccion.hidden = Number(clave) !== numero;
    }
    ui.pasos.forEach((paso) => {
      const valor = Number(paso.dataset.paso);
      const actual = valor === numero;
      const hecho = valor < numero;
      paso.classList.toggle("es-actual", actual);
      paso.classList.toggle("hecho", hecho);
      paso.classList.toggle("nohabilitado", valor > numero);
      if (actual) {
        paso.setAttribute("aria-current", "step");
        paso.tabIndex = 0;
      } else {
        paso.removeAttribute("aria-current");
        paso.tabIndex = -1;
      }
    });

    if (historial) {
      history.replaceState({ paso: numero }, "", `#paso-${numero}`);
    }

    /* foco según el paso */
    if (numero === 1) {
      ui.mensaje.focus();
    } else if (numero === 2) {
      ui.revision.focus();
    } else if (numero === 3) {
      ui.secciones[3].focus();
    } else if (numero === 4) {
      ui.veredicto.focus();
    }
  }

  function actualizarRiel(numero) {
    ui.pasos.forEach((paso) => {
      const valor = Number(paso.dataset.paso);
      paso.classList.toggle("es-actual", valor === numero);
      paso.classList.toggle("hecho", valor < numero);
      paso.classList.toggle("nohabilitado", valor > numero);
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

  function mostrarErrorDropzone(texto) {
    ui.errorDropzone.textContent = texto;
    ui.errorDropzone.hidden = false;
  }

  function limpiarErrorDropzone() {
    ui.errorDropzone.hidden = true;
    ui.errorDropzone.textContent = "";
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
    limpiarAviso();
    limpiarErrorDropzone();
  }

  function leerArchivoComoURL(archivo) {
    return new Promise((resolve, reject) => {
      const lector = new FileReader();
      lector.onload = () => resolve(lector.result);
      lector.onerror = () => reject(lector.error);
      lector.readAsDataURL(archivo);
    });
  }

  async function seleccionarArchivo(archivo) {
    limpiarErrorDropzone();
    if (
      archivo.type !== "image/png" &&
      archivo.type !== "image/jpeg"
    ) {
      mostrarErrorDropzone(mensajeDeError("formato_no_soportado"));
      ui.captura.value = "";
      archivoSeleccionado = null;
      ui.vistaPrevia.hidden = true;
      return;
    }
    if (archivo.size > LIMITE_IMAGEN_BYTES) {
      mostrarErrorDropzone(mensajeDeError("imagen_demasiado_grande"));
      ui.captura.value = "";
      archivoSeleccionado = null;
      ui.vistaPrevia.hidden = true;
      return;
    }

    archivoSeleccionado = archivo;
    ui.nombreArchivo.textContent = archivo.name;
    try {
      const url = await leerArchivoComoURL(archivo);
      ui.imagenVistaPrevia.src = url;
      ui.vistaPrevia.hidden = false;
    } catch {
      mostrarErrorDropzone(mensajeDeError("imagen_invalida"));
      ui.captura.value = "";
      archivoSeleccionado = null;
      ui.vistaPrevia.hidden = true;
    }
  }

  function quitarArchivo() {
    archivoSeleccionado = null;
    ui.captura.value = "";
    ui.vistaPrevia.hidden = true;
    ui.imagenVistaPrevia.src = "";
    ui.nombreArchivo.textContent = "";
    limpiarErrorDropzone();
    ui.captura.focus();
  }

  async function validarImagenLocalmente(archivo) {
    if (archivo.size > LIMITE_IMAGEN_BYTES) {
      throw { codigo: "imagen_demasiado_grande" };
    }
    if (
      archivo.type !== "image/png" &&
      archivo.type !== "image/jpeg"
    ) {
      throw { codigo: "formato_no_soportado" };
    }
    /* valida dimensiones leyendo la imagen */
    const url = await leerArchivoComoURL(archivo);
    await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = resolve;
      img.onerror = reject;
      img.src = url;
    });
    /* crear una imagen Offscreen para leer dimensiones reales */
    const bitmap = await createImageBitmap(await fetch(url).then((r) => r.blob()));
    if (bitmap.width > LADO_MAXIMO || bitmap.height > LADO_MAXIMO) {
      bitmap.close();
      throw { codigo: "imagen_demasiado_grande" };
    }
    bitmap.close();
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

    if (!archivoSeleccionado) {
      mostrarErrorDropzone(mensajeDeError("imagen_vacia"));
      ui.botonElegirArchivo.focus();
      return;
    }

    try {
      await validarImagenLocalmente(archivoSeleccionado);
    } catch (error) {
      mostrarErrorDropzone(mensajeDeError(error.codigo));
      ui.botonElegirArchivo.focus();
      return;
    }

    ui.botonPaso1.disabled = true;
    ui.botonPaso1.setAttribute("aria-busy", "true");
    ui.botonPaso1.textContent = "Extrayendo texto…";
    controladorAborto = new AbortController();
    try {
      const datos = new FormData();
      datos.append("imagen", archivoSeleccionado, archivoSeleccionado.name);
      const cuerpo = await llamarAPI("/api/analizar/imagen", {
        method: "POST",
        body: datos,
        signal: controladorAborto.signal,
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
      if (error.name === "AbortError") {
        limpiarAviso();
        return;
      }
      avisar(mensajeDeError(error.codigo));
    } finally {
      ui.botonPaso1.disabled = false;
      ui.botonPaso1.removeAttribute("aria-busy");
      ui.botonPaso1.textContent = "Analizar mensaje";
      controladorAborto = null;
    }
  }

  /* ---------------- paso 3 → 4: análisis y resultado ---------------- */

  function iniciarTemporizador() {
    inicioEspera = Date.now();
    ui.esperaTiempo.textContent = "Tiempo transcurrido: 0 s";
    clearInterval(temporizador);
    temporizador = setInterval(() => {
      const segundos = Math.floor((Date.now() - inicioEspera) / 1000);
      ui.esperaTiempo.textContent = `Tiempo transcurrido: ${segundos} s`;
    }, 1000);
  }

  function detenerTemporizador() {
    clearInterval(temporizador);
    temporizador = null;
    ui.esperaTiempo.textContent = "";
  }

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
    ui.secciones[3].focus();
    iniciarTemporizador();
    controladorAborto = new AbortController();
    try {
      const cuerpo = await llamarAPI("/api/analizar/texto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto }),
        signal: controladorAborto.signal,
      });
      detenerTemporizador();
      irAPaso(4);
      pintarResultado(cuerpo);
      ui.veredicto.focus();
    } catch (error) {
      detenerTemporizador();
      if (error.name === "AbortError") {
        irAPaso(2);
        return;
      }
      avisar(mensajeDeError(error.codigo));
      irAPaso(2);
      ui.revision.focus();
    } finally {
      ui.botonAnalizar.disabled = false;
      ui.botonAnalizar.removeAttribute("aria-busy");
      controladorAborto = null;
    }
  }

  function pintarResultado(r) {
    const clases = {
      verde: "veredicto--verde",
      amarillo: "veredicto--amarillo",
      rojo: "veredicto--rojo",
    };
    const colorBarra =
      r.estado === "rojo"
        ? "var(--rojo-borde)"
        : r.estado === "amarillo"
          ? "var(--ambar-borde)"
          : "var(--verde-borde)";
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
    const barra = document.querySelector("#medidor-veredicto .meter-barra");
    const medidor = document.getElementById("medidor-veredicto");
    const leyenda = document.getElementById("medidor-leyenda");
    if (barra) barra.style.backgroundColor = colorBarra;
    if (barra) barra.style.width = "0%";
    if (medidor) medidor.hidden = false;
    if (leyenda) leyenda.hidden = false;
    setTimeout(() => {
      if (barra) barra.style.width = `${Number(r.puntuacion)}%`;
    }, 60);

    /* anima el medidor tras un pequeño respiro */
    setTimeout(() => {
      const barra = ui.veredicto.querySelector(".meter-barra");
      if (barra) barra.style.width = `${Number(r.puntuacion)}%`;
    }, 60);

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

  function copiarRecomendaciones() {
    const lista = ui.detalle.querySelector(".recomendaciones");
    if (!lista) return;
    const textos = Array.from(lista.querySelectorAll("li")).map(
      (li) => li.textContent
    );
    const textoPlano = textos.join("\n");
    navigator.clipboard
      .writeText(textoPlano)
      .then(() => {
        const original = ui.botonCopiar.textContent;
        ui.botonCopiar.textContent = "Copiado";
        setTimeout(() => {
          ui.botonCopiar.textContent = original;
        }, 1500);
      })
      .catch(() => {
        mostrarToast("No se pudo copiar al portapapeles.");
      });
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

  /* ---------------- reinicio y retroceso ---------------- */

  function volverAEmpezar() {
    limpiarAviso();
    ui.revision.value = "";
    ui.avisosOCR.hidden = true;
    ui.avisosOCR.innerHTML = "";
    ui.detalle.innerHTML = "";
    ui.veredicto.className = "veredicto";
    ui.veredicto.innerHTML = "";
    document.getElementById("medidor-veredicto")?.setAttribute("hidden", "");
    document.getElementById("medidor-leyenda")?.setAttribute("hidden", "");
    historialPasos = [1];
    history.replaceState({ paso: 1 }, "", "#paso-1");
    irAPaso(1);
    ui.mensaje.focus();
  }

  function retrocederPaso() {
    const actual = Object.entries(ui.secciones).find(
      ([, seccion]) => !seccion.hidden
    );
    if (!actual) return;
    const numeroActual = Number(actual[0]);
    if (numeroActual === 2) {
      irAPaso(1);
      return;
    }
    if (numeroActual === 4) {
      irAPaso(2);
      return;
    }
    if (numeroActual === 3) {
      irAPaso(2);
      return;
    }
  }

  /* ---------------- eventos ---------------- */

  document.querySelectorAll('input[name="modo"]').forEach((entrada) => {
    entrada.addEventListener("change", () => {
      limpiarAviso();
      limpiarErrorDropzone();
      actualizarVisibilidadModo();
    });
  });

  ui.mensaje.addEventListener("input", actualizarContador);
  ui.botonPaso1.addEventListener("click", enviarDesdePaso1);

  /* zona de lanzamiento: click abre el input oculto */
  ui.zonaLanzamiento.addEventListener("click", () => {
    ui.captura.click();
  });
  ui.botonElegirArchivo.addEventListener("click", (e) => {
    e.stopPropagation();
    ui.captura.click();
  });

  /* drag & drop visual */
  ui.zonaLanzamiento.addEventListener("dragover", (e) => {
    e.preventDefault();
    ui.zonaLanzamiento.classList.add("arrastrando");
  });
  ui.zonaLanzamiento.addEventListener("dragleave", () => {
    ui.zonaLanzamiento.classList.remove("arrastrando");
  });
  ui.zonaLanzamiento.addEventListener("drop", (e) => {
    e.preventDefault();
    ui.zonaLanzamiento.classList.remove("arrastrando");
    const archivos = e.dataTransfer.files;
    if (archivos.length) seleccionarArchivo(archivos[0]);
  });

  ui.captura.addEventListener("change", () => {
    const archivo = ui.captura.files?.[0];
    if (archivo) seleccionarArchivo(archivo);
  });

  ui.quitarVista.addEventListener("click", quitarArchivo);

  ui.botonAnalizar.addEventListener("click", analizar);
  ui.botonVolverPaso2.addEventListener("click", () => {
    irAPaso(1);
  });
  ui.botonAtrasPaso4.addEventListener("click", retrocederPaso);
  ui.botonCopiar.addEventListener("click", copiarRecomendaciones);
  ui.botonOtro.addEventListener("click", volverAEmpezar);
  ui.botonCancelar.addEventListener("click", () => {
    if (controladorAborto) controladorAborto.abort();
    detenerTemporizador();
    irAPaso(2);
    ui.revision.focus();
  });

  window.addEventListener("popstate", (evento) => {
    if (evento.state && Number.isInteger(evento.state.paso)) {
      irAPaso(evento.state.paso, { historial: false });
    }
  });

  actualizarContador();
  actualizarVisibilidadModo();
  irAPaso(1);
})();
