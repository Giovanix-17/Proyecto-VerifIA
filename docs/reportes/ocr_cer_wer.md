# CER y WER del OCR (Fase 4)

> Generado por `scripts/eval_ocr.py` sobre 60 capturas sintéticas de `data/ocr_test` con transcripción de referencia.

## Configuración

| Componente | Valor |
|---|---|
| Tesseract | tesseract v5.5.3.20260724 |
| Binario | `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| Idioma | `spa` (`spa.traineddata`, tessdata_best) |
| Segmentación | `--oem 3 --psm 6`, `preserve_interword_spaces=1` |
| Preprocesamiento | gris → recorte → ampliación 2× si alto < 800 px → inversión en modo oscuro → denoise → normalización de fondo → Otsu |
| Recorte | caja relativa por captura: excluye barra de estado, encabezado y campo de escritura |

## Conjunto de evaluación

- 60 capturas sintéticas, 2 mensajes cada una (120 mensajes en total).
- 30 en modo claro y 30 en modo oscuro; 15 por cada resolución (720×1280, 1080×1920, 480×800 y 360×640).
- 30 imitando WhatsApp y 30 imitando la app de SMS.
- Solo mensajes de prueba; no se usaron datos personales reales.
- La referencia es el texto original de cada burbuja; se normalizan los espacios para que los saltos de línea no cuenten como error.

## Resultado global

- Capturas evaluadas: **60**
- Fallas del pipeline: **0**
- **CER macro: 0.14%** (meta de referencia ≤ 15%)
- **WER macro: 0.80%**
- CER micro (texto concatenado): **0.14%**
- CER mediana: **0.00%** · p90: **0.81%**
- Capturas con CER ≤ 15%: **60/60**

> **Lectura correcta:** las capturas son sintéticas y limpias (fuente digital, sin compresión de cámara ni fondos complejos). El CER real en capturas de teléfono será mayor; estas cifras miden el pipeline y sirven de línea base reproducible, no de garantía en campo.

## Por modo

| Modo | Capturas | CER macro | CER micro | WER macro | Exactas | CER > 15 % |
|---|---:|---:|---:|---:|---:|---:|
| claro | 30 | 0.2% | 0.2% | 1.0% | 26/30 | 0 |
| oscuro | 30 | 0.1% | 0.1% | 0.6% | 27/30 | 0 |

## Por resolución

| Resolución | Capturas | CER macro | CER micro | WER macro | Exactas | CER > 15 % |
|---|---:|---:|---:|---:|---:|---:|
| 1080x1920 | 15 | 0.0% | 0.0% | 0.0% | 15/15 | 0 |
| 360x640 | 15 | 0.5% | 0.5% | 3.2% | 8/15 | 0 |
| 480x800 | 15 | 0.0% | 0.0% | 0.0% | 15/15 | 0 |
| 720x1280 | 15 | 0.0% | 0.0% | 0.0% | 15/15 | 0 |

## Por tipo de app

| App | Capturas | CER macro | CER micro | WER macro | Exactas | CER > 15 % |
|---|---:|---:|---:|---:|---:|---:|
| sms | 28 | 0.2% | 0.2% | 1.2% | 24/28 | 0 |
| whatsapp | 32 | 0.1% | 0.1% | 0.5% | 29/32 | 0 |

## Peores capturas

| Captura | Condición | CER | WER | Referencia → hipótesis |
|---|---|---:|---:|---|
| captura-005 | claro, 360x640, sms | 1.8% | 10.5% | Su paquete llegó a la sucursal. Recoger con identificación. Tenemos un → Su paquete llegó a la sucursal. Recoger con identificación. Tenemos un |
| captura-039 | claro, 360x640, sms | 1.6% | 9.1% | Le informamos que su tarjeta termina en 1234 y fue usada en otro país. → Le informamos que su tarjeta termina en 1234 y fue usada en otro país. |
| captura-007 | claro, 360x640, sms | 1.0% | 6.2% | Le ofrecemos un préstamo inmediato sin aval. Su código de verificación → Le ofrecemos un préstamo inmediato sin aval. Su código de verificación |
| captura-052 | oscuro, 360x640, whatsapp | 1.0% | 5.9% | Su familiar tuvo un accidente. Envíe dinero urgente. Llame al 800 000  → Su familiar tuvo un accidente. Envíe dinero urgente, Llame al 800 000  |
| captura-040 | oscuro, 360x640, sms | 1.0% | 7.1% | Su código postal fue actualizado correctamente. Su suscripción fue ren → Su código postal fue actualizado correctamente. Su suscripción fue ren |

## Decisiones y límites

- Se probó binarización adaptativa; en modo oscuro generaba ruido en los bordes de las burbujas. La normalización de fondo + Otsu dio mejor CER y se usa como método principal; el adaptativo queda como respaldo si Otsu satura.
- La corrección `Q`/`G` → `@` solo se aplica dentro de una estructura de correo, porque Tesseract con `spa` confunde la arroba. Sin ella, un correo podría llegar sin enmascarar a la clasificación.
- Una captura con burbujas de polaridad mixta (texto claro sobre fondo oscuro dentro de una pantalla clara) no se resuelve con la inversión global; se documenta como caso residual.
- El recorte de encabezado es configurable y se desactiva si el usuario necesita el texto completo. La interfaz siempre muestra el borrador para corrección antes del análisis.
