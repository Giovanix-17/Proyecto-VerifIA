---
name: verifia-ocr
description: "Extrae texto de capturas de pantalla de apps de mensajería en español para VerifIA (Fase 4). Úsala al implementar o revisar el pipeline imagen→texto con OpenCV + Tesseract (paquete spa), al validar límites de imagen (5 MB, 4000 px, 12 MP), al ajustar preprocesamiento para modo claro/oscuro, o al medir CER y WER con ≥50 capturas. También al depurar texto mal reconocido antes de la sanitización."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, opencv-python-headless, pytesseract, pillow, jiwer. Requiere el binario tesseract con tessdata spa (paquete tesseract-ocr-spa en Debian). Sin red en ejecución."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-15"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §5, §6, §9 Fase 4, §15.1 (#5,#17)"
---

# OCR de capturas — VerifIA (Fase 4 / OE2)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. Si hay conflicto, gana la memoria.

## Regla de oro

**La imagen nunca sale del equipo.** No se envía al LLM ni a ningún servicio externo: se procesa en local,
se extrae el texto, y solo ese texto (tras sanitizar) puede viajar al modelo. Enviar la captura expondría
exactamente los datos personales que la sanitización elimina (decisión #17).

**El usuario siempre revisa el texto antes del análisis.** El resultado del OCR es un borrador editable, no
una verdad. La UI debe mostrar el texto extraído y permitir corregirlo antes de clasificar.

## 1. Validación de entrada (antes de tocar la imagen)

| Límite | Valor | Comportamiento |
|---|---|---|
| Tamaño de archivo | ≤ 5 MB | Rechazar con mensaje claro |
| Lado mayor | ≤ 4000 px | Rechazar; **no** reescalar hacia abajo silenciosamente |
| Resolución total | ≤ 12 MP | Aplica el primer límite alcanzado |
| Formatos | PNG, JPEG | Verificar por magic bytes, no por extensión |

Valida también que el archivo **decodifique**: un JPEG truncado debe dar error de usuario (422), no un 500.
Si se excede un límite, informa y detente; no "arregles" la entrada.

## 2. Preprocesamiento (OpenCV)

Orden recomendado, con justificación:

1. **Orientación EXIF**: aplica la rotación antes de cualquier otra cosa.
2. **Escala de grises** (`cvtColor` a `GRAY`): Tesseract trabaja mejor en luminancia.
3. **Ampliación**: si el alto útil es < ~800 px, escala 2× con `INTER_CUBIC`. Capturas pequeñas son la
   causa #1 de CER alto.
4. **Detección de modo oscuro**: si la mediana del histograma es baja (< ~110) o el fondo domina en negro,
   **invierte** (`bitwise_not`) antes de binarizar.
5. **Reducción de ruido**: `fastNlMeansDenoising` (h ± 10) o mediana 3×3. No abuses: difumina trazos finos.
6. **Binarización adaptativa**: `adaptiveThreshold` gaussiano, `blockSize` impar (~31–51 según ancho),
   `C` ≈ 10–15. Alternativa: Otsu cuando el contraste es bimodal y limpio.
7. **Recorte opcional**: elimina barras de estado, encabezados de la app y campos de escritura si aportan ruido.
   Hazlo **configurable** y desactivable: un recorte agresivo borra mensajes.

Nunca apliques el mismo preajuste a todas las capturas sin medir: registra qué variante usaste por imagen
para poder reproducir el CER.

## 3. Extracción con Tesseract

```python
import pytesseract
texto = pytesseract.image_to_string(
    img_bin,
    lang="spa",
    config="--oem 3 --psm 6 -c preserve_interword_spaces=1",
)
```

- `lang="spa"` es obligatorio; con `eng` los acentos y la ñ se degradan.
- **PSM**: `6` (bloque uniforme) para capturas de chat; `4` (columna de tamaños variables) si hay burbujas
  muy dispares; `11`/`12` solo para texto disperso. Documenta el elegido.
- `--oem 3` (LSTM) es el predeterminado recomendado.
- Verifica al arrancar que `spa.traineddata` existe; falla rápido y con mensaje explícito si no.
- En Docker, fija `TESSDATA_PREFIX` para evitar descargas en runtime (y fallos sin red).

## 4. Posprocesamiento

1. **Unir líneas del mismo globo**: agrupa líneas cuya separación vertical sea menor que ~1.5× la altura
   media de línea y cuya alineación horizontal se solape.
2. **Eliminar marcas de hora** (`12:34`, `12:34 p.m.`) y separadores de fecha del encabezado.
3. **Normalizar** espacios múltiples, saltos triples y caracteres de control.
4. **Correcciones conservadoras**: solo confusiones de alta confianza y con contexto (`0`↔`O` dentro de
   palabras, `l`↔`I`). **No** "corrijas" palabras completas: inventar texto altera la señal de fraude.
5. **Conserva** signos de dinero, porcentajes y URLs: son señal para el clasificador.

## 5. Evaluación (≥50 capturas)

- Set en `data/ocr_test/`: capturas de apps de mensajería comunes en México y del servicio de SMS,
  **modo claro y oscuro**, varias resoluciones, **solo mensajes de prueba** (sin datos personales reales).
- Transcripción manual por captura como referencia.
- Métricas con `jiwer`:

```python
import jiwer
cer = jiwer.cer(referencia, hipotesis)
wer = jiwer.wer(referencia, hipotesis)
```

- **Meta de referencia: CER ≤ 15 %** en capturas de calidad aceptable. Si no se alcanza, ajusta el
  preprocesamiento **antes** de tocar el clasificador.
- Reporta CER/WER **desagregado** por modo (claro/oscuro), resolución y tipo de captura. Un promedio global
  esconde el caso que falla.
- Si la imagen es insuficiente (borrosa, recortada), dilo al usuario en lugar de devolver basura.

## 6. Integración con el pipeline

```
imagen → validar límites → preprocesar → Tesseract(spa) → posprocesar
       → mostrar texto editable al usuario → sanitizar → clasificar
```

- El texto del OCR **no** se guarda (regla 2). Se mantiene en memoria durante la petición.
- Si el OCR devuelve < ~10 caracteres útiles, trata como "no se pudo extraer" y pide otra captura.
- No pases el texto del OCR directamente al clasificador: primero la sanitización (regla 1).

## 7. Pruebas

| Caso | Esperado |
|---|---|
| PNG 6 MB | 413/422 con mensaje de tamaño |
| Imagen 5000 px | rechazo por lado mayor |
| JPEG corrupto | 422, no 500 |
| Captura modo oscuro | se invierte y el texto se extrae |
| Captura con emojis | emojis no rompen el texto; se conservan solo si aportan |
| Imagen en blanco | mensaje "no se pudo extraer texto" |
| Captura con teléfono | el teléfono llega intacto a la sanitización (ahí se enmascara) |

## Criterios de aceptación (Fase 4)

- Pipeline imagen→texto funcional y enlazado con la sanitización.
- Límites aplicados y probados.
- CER/WER medidos sobre ≥50 capturas, con tabla por condición.
- Texto mostrado al usuario para corrección antes del análisis.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| Acentos y ñ incorrectos | `lang` no es `spa` | Instala `tesseract-ocr-spa` y fija `lang="spa"` |
| Texto vacío en modo oscuro | No se invirtió la imagen | Detecta luminancia y aplica `bitwise_not` |
| Caracteres rotos en letra fina | Umbral adaptativo demasiado agresivo | Sube `blockSize`/`C` o usa Otsu |
| Líneas partidas por burbuja | Sin agrupación vertical | Une por proximidad y solape horizontal |
| CER alto en capturas pequeñas | Sin ampliación | Escala 2× antes de binarizar |
| Funciona en local y falla en Docker | Falta el binario o `spa.traineddata` | Instala Tesseract + spa en la imagen |
| El texto contiene horas y nombres de app | Falta recorte de encabezado | Recorte configurable + regex de timestamps |
