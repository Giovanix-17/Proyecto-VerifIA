# Wireframes de la interfaz — VerifIA (Fase 7, mejoras)

> Bocetos de baja fidelidad previos a la implementación (memoria §9 Fase 7:
> *"Bocetos de baja fidelidad antes de implementar"*). Fuente de verdad:
> `VerifIA_memoria_proyecto.md`; detalle operativo: skill `verifia-api-docker`.
> Documenta la versión mejorada de la interfaz (dropzone, medidor, botón Atrás,
> copiar recomendaciones, tipografía Atkinson Hyperlegible local).

## 1. Objetivo y audiencia

- **Usuario:** cualquier persona en México que recibe un mensaje sospechoso y
  quiere saber si es fraude **antes de actuar**. Sin conocimientos técnicos.
- **Trabajo principal de la pantalla:** pegar un mensaje o subir una captura y
  recibir un veredicto claro (semáforo) con la acción recomendada.
- **Tono:** tranquilo y claro. La herramienta informa, no alarmista. El
  veredicto y la acción principal van primero; el detalle después.
- **Voz:** segunda persona ("tú") y recomendaciones impersonales, sin
  inventar teléfonos, enlaces ni instituciones.

## 2. Decisiones de diseño

### 2.1 Tipografía: Atkinson Hyperlegible (local)

Se usa **Atkinson Hyperlegible** en sus cuatro variantes (Regular/Bold ×
Latin/Latin-ext), servidas como archivos `.woff2` locales bajo
`web/fuentes/` y precargadas con `<link rel="preload">`. No hay CDN ni
conexión externa para la interfaz (privacidad y ejecución offline). La pila
del sistema es el fallback.

- Base 17 px en desktop, 16 px en móvil; interlineado 1.55.
- Veredicto: 1.45–1.65 rem, peso 700.
- Etiquetas de paso y botones: 1 rem, peso 600. Nada en mayúsculas sostenidas.

### 2.2 Paleta (4 tonos + semáforo)

| Uso | Hex | Nota de contraste |
|---|---|---|
| Fondo (`papel`) | `#F1F4F6` | Gris frío claro |
| Tinta (texto) | `#1B2A32` | ≥ 12:1 sobre el fondo |
| Primario (acciones) | `#0E5A66` | ≥ 6:1 con texto blanco |
| Bordes/superficies | `#FFFFFF` + `#C6D2D8` | Bordes ≥ 3:1 contra el fondo |
| Verde (riesgo bajo) | texto `#176B2C` sobre tinte `#E3F3E6` | ≥ 4.5:1 |
| Amarillo (riesgo medio) | texto `#7A5200` sobre tinte `#FFF3D6` | ≥ 4.5:1 |
| Rojo (riesgo alto) | texto `#B3261E` sobre tinte `#FDEBEA` | ≥ 4.5:1 |

El semáforo usa **texto + icono + color**: el color es el tercer canal, no el
primero (WCAG 1.4.1). Los tres estados tienen icono distinto (✓, !, ✕) y
palabra ("Riesgo bajo/medio/alto").

### 2.3 Layout

Una columna, contenido centrado con máximo 640 px. Los cuatro pasos son una
secuencia real representada como un **riel de botones conectados** (cada paso
es un botón navegable). En escritorio el riel queda horizontal arriba; en
móvil, compacto.

## 3. Bocetos

### Paso 1 — Entrada (hero de la página)

```
┌──────────────────────────────────────────────┐
│  VerifIA                                     │
│  ¿Recibiste un mensaje sospechoso?           │
│  Verifícalo aquí antes de responder.         │
│                                              │
│  (1)──(2)──(3)──(4)   ← riel de botones      │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ [ Pegar texto ]  [ Subir captura ]     │  │ ← radios (segmented)   │
│  ├────────────────────────────────────────┤  │
│  │ textarea (maxlength 10000)             │  │ ← modo texto           │
│  │                            132/10000   │  │                          │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │ ← modo imagen (dropzone)
│  │ ⬆  Solta tu captura aquí               │  │                          │
│  │     o [ Elegir archivo ]               │  │ ← input oculto + botón   │
│  │     PNG o JPEG, hasta 5 MB             │  │                          │
│  │                                        │  │                          │
│  │  [vista previa]  [× quitar]            │  │ ← aparece tras seleccionar│
│  └────────────────────────────────────────┘  │                          │
│  [error: formato/tamaño]                     │  ← inline, rojo          │
│                                              │
│  [ Analizar mensaje ]                        │  ← botón primario        │
│                                              │
│  🔒 Privacidad: ...                          │  ← visible antes de escribir│
│                                              │
└──────────────────────────────────────────────┘
```

- La zona de lanzamiento es un `<div role="region">` con estilo de dropzone:
  arrastre y soltar, estados `:hover` y `.arrastrando`, input de archivo
  oculto (`<input type="file" hidden>`) y botón visible "Elegir archivo".
- Tras seleccionar, se muestra una vista previa (miniatura + nombre) con
  botón para quitarla.
- Validación local async: tipo MIME, ≤ 5 MB, ≤ 4000 px por lado.

### Paso 2 — Revisión del texto extraído

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│  Revisa el texto antes de analizarlo         │
│  Si algo se leyó mal en tu captura, corrígelo│
│  aquí.                                       │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ textarea editable (9 filas)            │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  [ Atrás ]   [ Analizar este texto ]         │
└──────────────────────────────────────────────┘
```

- "Atrás" vuelve al paso 1.
- Los avisos del OCR (advertencias de extracción) se muestran arriba del
  textarea.

### Paso 3 — Análisis (estado de espera)

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│      ◌  Analizando tu mensaje…               │  ← spinner + aria-live
│                                              │
│      Tiempo transcurrido: 4 s                │  ← temporizador honesto  │
│                                              │
│      [ Cancelar ]                            │  ← AbortController       │
└──────────────────────────────────────────────┘
```

- Spinner respeta `prefers-reduced-motion` (se detiene).
- "Cancelar" aborta la petición (`AbortController`) y vuelve al paso 2.

### Paso 4 — Resultado (el veredicto es el hero)

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ ⛔  RIESGO ALTO                          │ │ ← icono + palabra + color│
│ │ Probable suplantación bancaria   93/100 │ │ ← puntuación + medidor   │
│ │ No actúes conforme al mensaje.           │ │ ← acción principal       │
│ │                                          │ │   [██████████░░░░░░░░]  │
│ │  Riesgo bajo    Riesgo medio  Riesgo alto│ │                          │
│ └──────────────────────────────────────────┘ │                          │
│                                              │
│  En pocas palabras: ...                      │ │                          │
│  Señales de alerta: ...                      │ │                          │
│  Lo que puedes hacer:                        │ │                          │
│  1. ...                                      │ │                          │
│                                              │
│  [ Atrás ] [ Copiar recomendaciones ]        │ │ ← copia solo el catálogo │
│  [ Analizar otro mensaje ]                   │ │     (nunca el mensaje)   │
└──────────────────────────────────────────────┘
```

- Medidor de puntuación (0–100) con barra de color según el estado.
- "Copiar recomendaciones" copia solo las recomendaciones del catálogo al
  portapapeles y confirma visualmente ("Copiado").
- "Atrás" vuelve al paso 2; "Analizar otro mensaje" reinicia el flujo.
- `<details>` para ver el mensaje analizado (datos ya enmascarados).
- Aviso orientativo obligatorio al final.

## 4. Estados de error

| Caso | Mensaje |
|---|---|
| Texto vacío | "Escribe el mensaje que quieres verificar." |
| Texto > 10 000 caracteres | "El mensaje es demasiado largo (máximo 10 000 caracteres)." |
| Imagen no PNG/JPEG | "Solo se admiten imágenes PNG o JPEG." |
| Imagen > 5 MB / 4000 px | "La imagen es demasiado grande (máximo 5 MB o 4000 px por lado)." |
| Imagen vacía | "Selecciona una captura PNG o JPEG." |
| Imagen inválida | "La imagen no se pudo leer. Inténtala con otra captura." |
| OCR insuficiente | "No se pudo extraer texto suficiente. Usa una captura más nítida." |
| Demasiadas solicitudes | "Estás enviando mensajes muy rápido. Espera unos segundos." |
| Servicio no disponible | "El servicio no está disponible ahora. Inténtalo más tarde." |

Los errores se anuncian con `role="alert"` y el foco se mueve al campo que
los causó, sin perder el contenido escrito.

## 5. Navegación e historial

- Cada paso del riel es un botón navegable (`role="button"`, `tabindex`).
- El botón "Atrás" del paso 2 vuelve al paso 1; el del paso 4 vuelve al paso 2.
- El historial se mantiene en una pila interna (`historialPasos`) y se refleja
  en `history.pushState` / `popstate` para que el botón Atrás del navegador
  sea coherente.
- Al reiniciar ("Analizar otro mensaje"), el historial se resetea al paso 1.

## 6. Checklist de accesibilidad (WCAG 2.1 AA)

- [x] Contraste ≥ 4.5:1 en texto normal; ≥ 3:1 en bordes/iconos.
- [x] Riesgo comunicado con icono + palabra + color (1.4.1).
- [x] Todo campo con `<label>`; el contador se asocia con `aria-describedby`.
- [x] Navegación completa por teclado; `:focus-visible` evidente (3 px).
- [x] `aria-live="polite"` en espera y resultado; `role="alert"` en errores.
- [x] Botones ≥ 48×48 px; base tipográfica ≥ 16 px; sin scroll horizontal.
- [x] `prefers-reduced-motion` respetado (sin animaciones esenciales).
- [x] Lenguaje sin tecnicismos; voz "tú"; recomendaciones impersonales.
- [x] Aviso de privacidad visible en el paso 1; aviso orientativo en cada
  resultado.
- [x] Sin CDN: fuentes y recursos locales.

## 7. Criterio de salida

La implementación (`web/`) sigue este documento. Cambios visuales posteriores
se documentan aquí.

**Actualizado (20/11/2026):** dropzone con "Elegir archivo", vista previa,
medidor de puntuación, botón "Copiar recomendaciones", botón "Atrás" con
historial, tipografía Atkinson Hyperlegible local, voz "tú" y recomendaciones
impersonales.
