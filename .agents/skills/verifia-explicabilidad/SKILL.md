---
name: verifia-explicabilidad
description: "Convierte el dictamen de VerifIA en algo comprensible para un ciudadano (Fase 6): semáforo de 3 estados desde la puntuación, señales de alerta resaltadas sobre el texto sanitizado, resumen en lenguaje sencillo y catálogo de recomendaciones por tipología. Úsala al implementar el módulo explain/, al redactar el catálogo de acciones seguras, al mapear términos del modelo lineal a señales, o al revisar que el resultado sea accesible y no alarmista."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, pydantic v2, scikit-learn (coeficientes del modelo lineal). Sin dependencias nuevas."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-16"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §7 (reglas 6, 11, 13), §8.5, §8.6, §9 Fase 6, §12"
---

# Explicabilidad y recomendaciones — VerifIA (Fase 6)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. Si hay conflicto, gana la memoria.

## Invariantes

1. **Las recomendaciones salen de un catálogo predefinido por tipología.** El LLM **nunca** las redacta:
   así no puede inventar teléfonos, enlaces ni trámites (regla 6).
2. **El aviso de que la herramienta es orientativa es obligatorio** en todo resultado (regla 13).
3. **El color no es el único canal.** Cada estado lleva texto e icono (WCAG 2.1).
4. **Este módulo no decide.** Recibe tipología y puntuación ya calculadas; no las recalcula ni las corrige.
5. **Determinismo.** Mismo dictamen → mismo resumen. Nada de aleatoriedad ni de generación libre.

## 1. Semáforo

| Color | Puntuación | `nivel_riesgo` | Mensaje al usuario | Acción |
|---|---|---|---|---|
| Verde | 0–33 | `bajo` | "No se detectaron señales claras de fraude" | Puede continuar, con precaución |
| Amarillo | 34–66 | `medio` | "Hay señales que conviene verificar" | Verificar por un canal oficial antes de actuar |
| Rojo | 67–100 | `alto` | "Este mensaje tiene señales fuertes de fraude" | No actuar conforme al mensaje |

Deriva el estado **de la puntuación final**, nunca del `nivel_riesgo` que devolvió el LLM. La banda y la
puntuación deben coincidir; si no, es un error de programación, no una decisión de diseño.

```python
def estado(puntuacion: int) -> tuple[str, str, str]:
    if puntuacion <= 33:
        return "verde", "bajo", "Riesgo bajo"
    if puntuacion <= 66:
        return "amarillo", "medio", "Riesgo medio"
    return "rojo", "alto", "Riesgo alto"
```

Cada estado incluye `etiqueta`, `icono` y `descripcion` en la respuesta; la UI no debe inferir nada del color.

## 2. Señales de alerta

### Desde el Nivel 2
El LLM ya devuelve `senales_alerta` con `frase` + `motivo`, y el esquema obliga a que `frase` aparezca en el
texto sanitizado. Úsalo tal cual; si una frase no se localiza, descártala (ver `verifia-nivel2-llm`).

### Desde el Nivel 1 (modelo lineal)

1. Con el `Pipeline` entrenado, obtén los términos con mayor contribución **para la clase predicha**:
   `coef[clase] × tfidf[fila]`, ordena descendente y toma los `k` primeros (k = 3–5).
2. Filtra términos no informativos: stopwords, tokens de una sola letra, fragmentos de menos de 3 caracteres.
3. **Conserva** los marcadores (`[TELEFONO]`, `[ENLACE:...]`, `[CODIGO]`): son señal legítima.
4. Localiza el término en el texto sanitizado de forma **insensible a mayúsculas y acentos**, y marca el span.
5. Si el término no aparece literalmente (por tokenización de n-gramas), omítelo: no resaltes nada inventado.

```python
def spans_de_terminos(texto: str, terminos: list[str]) -> list[tuple[int, int, str]]:
    # normaliza solo para comparar; los offsets se calculan sobre el texto original
    spans, usados = [], set()
    for t in terminos:
        i = texto.lower().find(t.lower())
        while i != -1 and any(a <= i < b for a, b in usados):
            i = texto.lower().find(t.lower(), i + 1)
        if i != -1:
            spans.append((i, i + len(t), t))
            usados.add((i, i + len(t)))
    return spans
```

**Límite**: máximo 5 señales en pantalla. Más de cinco no informa: abruma.

### Mapeo término → señal

Traduce el término a una categoría comprensible, no lo muestres crudo:

| Término | `senales_alerta` |
|---|---|
| `urgente`, `hoy`, `24 horas`, `último aviso` | `urgencia` |
| `bloqueada`, `cancelar`, `demanda`, `multa` | `amenaza` |
| `banco`, `BBVA`, `Banorte`, `SAT` + solicitud | `suplantacion` |
| `código`, `NIP`, `token`, `contraseña`, `[CODIGO]` | `solicitud_datos` |
| `[ENLACE:...]`, `bit.ly`, `verifica aquí` | `enlace_sospechoso` |

## 3. Resumen legible

Plantilla determinista de **máximo 3 frases**, en este orden:

1. **Qué se detectó**: tipología en lenguaje llano.
2. **Señal más relevante**: la de mayor peso, con su motivo.
3. **Consecuencia de actuar**: qué puede pasar si hace caso.

```python
PLANTILLA = (
    "El mensaje se parece a {tipologia_llana}. "
    "La señal más importante es: {senal}. "
    "{consecuencia}"
)

CONSECUENCIA = {
    "suplantacion_bancaria": "Si comparte el código, otra persona podría autorizar cargos en su cuenta.",
    "paqueteria_retenida": "Si paga o da sus datos en ese enlace, el cobro o el robo de datos puede ocurrir de inmediato.",
    "oferta_laboral_fraudulenta": "Si adelanta dinero o entrega documentos, es muy probable que no recupere el pago.",
    "extorsion": "Responder o pagar suele aumentar la presión y las exigencias.",
    "legitimo": "Aun así, verifique por un canal oficial si algo le parece extraño.",
}
```

Reglas de redacción:

- Frases cortas, ≤ 18 palabras. Sin tecnicismos ("TF-IDF", "cascada", "probabilidad calibrada").
- **Sin segunda persona acusatoria.** Nada de "usted fue negligente" o "debió desconfiar": en extorsión
  esto revictimiza y reduce la confianza.
- Sin cifras inventadas ni "99 % de certeza". La orientación es cualitativa.
- Si `fuente_diccionario == "nivel_1_fallback"`, añade de forma visible: *"análisis parcial: el modelo
  avanzado no estuvo disponible"*.

## 4. Catálogo de recomendaciones

Estructura: recomendaciones **generales** (siempre 2) + **por tipología** (3–4). Sin llamadas al LLM, sin
texto libre generado.

| Tipología | Recomendaciones |
|---|---|
| `legitimo` | Verificar por el canal oficial si algo le parece raro · No compartir datos si no inició el trámite |
| `suplantacion_bancaria` | No compartir códigos, NIP, token ni contraseñas · No entrar al enlace del mensaje · Llamar al número del reverso de su tarjeta · Revisar movimientos en la app oficial |
| `paqueteria_retenida` | Rastrear el envío solo en el sitio oficial de la paquetería · No pagar "ajustes" ni "liberaciones" por enlace · Confirmar el pedido con quien lo envió |
| `oferta_laboral_fraudulenta` | No pagar anticipos, capacitación ni "equipo" · No entregar INE, CURP ni datos bancarios antes de un contrato · Verificar la empresa en su sitio oficial |
| `extorsion` | No responder ni negociar · No pagar · Conservar el mensaje como evidencia · Denunciar (911 / Fiscalía) y buscar apoyo |

Generales (siempre presentes):

- "Conservar el mensaje como evidencia (captura de pantalla) antes de borrarlo."
- "Ante cualquier duda, verificar por un canal oficial que usted consiga por su cuenta."

**Regla dura del catálogo**: ninguna recomendación contiene teléfonos, correos, URL ni nombres de
instituciones que no estén en una lista constante verificada y citada. Si se necesita un número, va como
constante con fuente documentada en el código, no como texto libre.

## 5. Contrato de salida

```python
class Explicacion(BaseModel):
    estado: Literal["verde", "amarillo", "rojo"]
    nivel_riesgo: Literal["bajo", "medio", "alto"]
    titulo: str
    resumen_legible: str
    senales_alerta: list[Senal]        # máximo 5
    recomendaciones: list[str]         # catálogo, 3–6
    advertencias: list[str]            # incluye "análisis parcial" si aplica
    aviso: str                         # obligatorio, regla 13
```

El campo `aviso` es constante y no depende del dictamen.

## 6. Pruebas

1. **Snapshot** del resumen para cada una de las 5 tipologías × 3 estados (15 casos): el texto no cambia sin
   revisión explícita.
2. **Determinismo**: dos llamadas con el mismo dictamen producen exactamente el mismo resultado.
3. **Catálogo**: ninguna recomendación contiene `http`, `www`, `@` ni secuencias de 8+ dígitos (salvo 911).
4. **Aviso**: presente en el 100 % de las respuestas, incluida la ruta de fallback.
5. **Señales**: nunca más de 5; ninguna con `frase` ausente del texto sanitizado.
6. **Accesibilidad**: el estado incluye etiqueta e icono; la UI no depende del color.

## Criterios de aceptación (Fase 6)

- Semáforo derivado de la puntuación y coherente con la banda.
- Señales resaltadas sobre el texto sanitizado, con origen trazable (Nivel 1 o Nivel 2).
- Resumen en lenguaje sencillo con señal, peligro y consecuencia.
- Recomendaciones 100 % de catálogo.
- Aviso orientativo siempre visible.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| Recomendaciones distintas cada vez | Se le pide al LLM que las redacte | Usa el catálogo, sin excepciones |
| Enlaces o teléfonos inventados | Texto libre generado | Constantes verificadas o ninguna cifra |
| Colores invertidos | Se derivó del `nivel_riesgo` del LLM | Deriva siempre de la puntuación |
| Se resalta texto que no existe | Término de n-grama sin coincidencia literal | Omite el span |
| Tono culpabilizante | Plantilla con "usted debió" | Revisa redacción; en extorsión es crítico |
| Usuario cree que es un veredicto | Falta el aviso orientativo | Constante en todas las respuestas |
