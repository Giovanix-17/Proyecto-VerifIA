# Wireframes de la interfaz — VerifIA (Fase 7, tarea 7.1)

> Bocetos de baja fidelidad previos a la implementación (memoria §9 Fase 7:
> *"Bocetos de baja fidelidad antes de implementar"*). Fuente de verdad:
> `VerifIA_memoria_proyecto.md`; detalle operativo: skill `verifia-api-docker`.

## 1. Objetivo y audiencia

- **Usuario:** cualquier persona en México que recibe un mensaje sospechoso y
  quiere saber si es fraude **antes de actuar**. Sin conocimientos técnicos.
- **Trabajo principal de la pantalla:** pegar un mensaje o subir una captura y
  recibir un veredicto claro (semáforo) con la acción recomendada.
- **Tono:** tranquilo y claro. La herramienta informa, no alarmista. El
  veredicto y la acción principal van primero; el detalle después.

## 2. Decisiones de diseño

### 2.1 Paleta (4 tonos + semáforo)

| Uso | Hex | Nota de contraste |
|---|---|---|
| Fondo (`papel`) | `#F1F4F6` | Gris frío claro; evita el crema genérico |
| Tinta (texto) | `#1B2A32` | ≥ 12:1 sobre el fondo |
| Primario (acciones, enlaces) | `#0E5A66` | ≥ 6:1 con texto blanco encima |
| Bordes/superficies | `#FFFFFF` + `#C6D2D8` | Bordes ≥ 3:1 contra el fondo |
| Verde (riesgo bajo) | texto `#176B2C` sobre tinte `#E3F3E6` | ≥ 4.5:1 |
| Amarillo (riesgo medio) | texto `#7A5200` sobre tinte `#FFF3D6` | ≥ 4.5:1 |
| Rojo (riesgo alto) | texto `#B3261E` sobre tinte `#FDEBEA` | ≥ 4.5:1 |

El semáforo usa **texto + icono + color**: el color es el tercer canal, no el
primero (WCAG 1.4.1). Los tres estados tienen icono distinto (✓, !, ✕) y
palabra ("Riesgo bajo/medio/alto").

### 2.2 Tipografía

Sin fuentes externas: **no se cargan CDNs** (privacidad y ejecución local sin
red, §5: la imagen nunca sale del equipo; el prototipo funciona offline). Se
usa la pila del sistema con una escala deliberada:

- Base 17 px en móvil (≥ 16 px exigido por la skill), interlineado 1.55.
- Veredicto: 1.6–2.0 rem, peso 700, la única pieza "grande" de la página.
- Etiquetas de paso y botones: 1 rem, peso 600. Nada en mayúsculas sostenidas.
- Longitud de línea ≤ 75 caracteres en párrafos.

### 2.3 Layout

Una columna, contenido centrado con máximo 640 px. Los cuatro pasos son una
secuencia real, así que llevan numeración (1–4) en un riel de progreso. En
escritorio el riel queda horizontal arriba; en móvil, vertical compacta.

## 3. Bocetos

### Paso 1 — Entrada (hero de la página)

```
┌──────────────────────────────────────────────┐
│  VerifIA                                     │
│  ¿Recibiste un mensaje sospechoso?           │
│  Verifícalo aquí antes de responder.         │
│                                              │
│  (1)──(2)──(3)──(4)   ← riel de progreso     │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ [ Pegar texto ]  [ Subir captura ]     │  │ ← dos pestañas (radio)
│  ├────────────────────────────────────────┤  │
│  │ textarea (maxlength 10000)             │  │
│  │                            132/10000   │  │
│  │ [ Analizar mensaje ]        (≥44 px)   │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  🔒 Privacidad: tu mensaje se enmascara      │
│  (teléfonos, correos, nombres) y NO se       │
│  guarda. Todo el análisis ocurre en tu       │
│  computadora.                                │
│                                              │
│  Esta herramienta es orientativa. No         │
│  sustituye tu criterio ni una denuncia.      │
└──────────────────────────────────────────────┘
```

- Pestaña "Subir captura": input de archivo PNG/JPEG + texto de ayuda con los
  límites (hasta 5 MB, 4000 px).
- El aviso de privacidad es visible **antes** de escribir, no en el pie.

### Paso 2 — Revisar texto extraído

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│  Revisa el texto de tu captura               │
│  Corrige lo que se haya leído mal:           │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ textarea editable (texto OCR o el      │  │
│  │ texto pegado, para confirmar)          │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ⚠ Si tu captura salió borrosa: "No se pudo  │  ← errores del OCR en
│  extraer texto suficiente…"                  │     lenguaje claro
│                                              │
│  [ Corregir y analizar ]                     │
│  [ Volver a empezar ]                        │
└──────────────────────────────────────────────┘
```

Con texto pegado directamente, el paso 2 se muestra como confirmación breve
("Así vamos a analizar tu mensaje") con el mismo textarea editable.

### Paso 3 — Análisis (estado de espera)

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│      ◌  Analizando tu mensaje…               │  ← spinner + texto
│                                              │     (aria-live)
│      Puede tardar unos segundos.             │
│      [ Botón deshabilitado durante la        │
│        espera ]                              │
└──────────────────────────────────────────────┘
```

### Paso 4 — Resultado (el veredicto es el hero)

```
┌──────────────────────────────────────────────┐
│ (1)──(2)──(3)──(4)                           │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ ✕  RIESGO ALTO                           │ │ ← icono + palabra + color
│ │ Probable suplantación bancaria    92/100 │ │    en una sola tarjeta
│ │                                          │ │
│ │ No actúes conforme al mensaje. No        │ │ ← acción principal
│ │ compartas códigos ni pagos.              │ │    primero (Fase 6)
│ └──────────────────────────────────────────┘ │
│                                              │
│  Por qué: "su cuenta será bloqueada hoy"     │ ← señales resaltadas
│  → urgencia y amenaza.                       │    (cita literal + motivo)
│                                              │
│  Lo que puedes hacer:                        │
│  1. No compartas códigos ni contraseñas.     │ ← catálogo cerrado
│  2. Llama a tu banco al número de tu         │    (regla 6: nunca
│     tarjeta.                                 │    inventado por la IA)
│  3. Conserva el mensaje como evidencia.      │
│                                              │
│  ▸ Ver el mensaje analizado                  │ ← <details>: texto ya
│  ┌────────────────────────────────────────┐  │    enmascarado con las
│  │ Su cuenta será bloqueada… [TELEFONO]   │  │    señales subrayadas
│  └────────────────────────────────────────┘  │
│                                              │
│  ⚠ Análisis parcial: el modelo avanzado no   │ ← solo si hubo fallback
│  estuvo disponible.                          │    (regla 8)
│                                              │
│  Esta herramienta es orientativa. No         │ ← aviso obligatorio
│  sustituye tu criterio ni una denuncia.      │    (regla 13)
│                                              │
│  [ Analizar otro mensaje ]                   │
└──────────────────────────────────────────────┘
```

## 4. Estados de error (siempre anunciados, no solo pintados)

| Caso | Mensaje en pantalla |
|---|---|
| Texto vacío / solo espacios | "Escribe el mensaje que quieres verificar." |
| Texto > 10 000 caracteres | "El mensaje es demasiado largo (máximo 10 000 caracteres)." |
| Archivo no PNG/JPEG | "Solo se admiten imágenes PNG o JPEG." |
| Imagen > 5 MB / 4000 px / 12 MP | "La imagen es demasiado grande. Reduce su tamaño e inténtalo de nuevo." |
| OCR sin texto suficiente | "No se pudo extraer texto suficiente. Intenta con una captura más nítida." |
| Demasiadas solicitudes (429) | "Espera un momento antes de analizar otro mensaje." |
| Error del servidor | "No se pudo completar el análisis. Inténtalo de nuevo." |

Los errores se anuncian con `role="alert"` / `aria-live="assertive"` y el foco
se mueve al mensaje, sin perder el contenido escrito.

## 5. Checklist de accesibilidad (WCAG 2.1 AA)

- [x] Contraste ≥ 4.5:1 en texto normal; ≥ 3:1 en bordes/iconos.
- [x] Riesgo comunicado con icono + palabra + color (1.4.1).
- [x] Todo campo con `<label>`; el contador se asocia con `aria-describedby` y no se anuncia en cada pulsación para no interrumpir.
- [x] Navegación completa por teclado; `:focus-visible` evidente; orden lógico.
- [x] Zona de resultado con `aria-live="polite"`; errores con `role="alert"`; foco en el veredicto al terminar.
- [x] Botones ≥ 44×44 px; base tipográfica ≥ 16 px; sin scroll horizontal.
- [x] `prefers-reduced-motion` respetado (sin animaciones esenciales).
- [x] Lenguaje sin tecnicismos (nada de "TF-IDF", "cascada" o "Nivel 1/2" en la UI).
- [x] Aviso de privacidad visible en el paso 1; aviso orientativo en cada resultado.

La verificación con ratios de contraste, teclado y E2E está en
[`docs/reportes/interfaz_web.md`](reportes/interfaz_web.md) §8 y §9.

## 6. Criterio de salida de la tarea

Bocetos revisados por el desarrollador; la implementación (`web/`) sigue este
documento. Cambios visuales posteriores se documentan aquí.

**Cierre (19/11/2026).** La implementación se verificó con `tests/test_interfaz.py`,
`scripts/e2e_interfaz.py` y una revisión de contraste WCAG. El aviso de privacidad
se amplió para aclarar que, en casos ambiguos, solo el texto ya enmascarado se
consulta a un servicio externo; la captura nunca sale del equipo.
