# Protocolo de usabilidad SUS — VerifIA (Fase 8, §7 del skill)

> **Estado:** protocolo y materiales listos. La aplicación con 10–15 voluntarios reales está pendiente de ejecución (requiere personas físicas; el agente no puede reclutar ni obtener consentimiento de terceros). Los materiales quedan listos para que el desarrollador los aplique.

---

## 1. Objetivo

Medir la usabilidad percibida del prototipo VerifIA con el cuestionario **SUS** (System Usability Scale, 10 ítems, escala 0–100) y comparar las decisiones de los usuarios **antes y después** de ver la alerta del sistema.

---

## 2. Participantes

| Criterio | Valor |
|---|---|
| **n** | 10–15 voluntarios |
| **Perfil** | Distintas edades y distintos niveles de familiaridad con tecnología |
| **Consentimiento** | Informado, por escrito, antes de empezar |
| **Datos recogidos** | Ningún dato identificable; solo edad (rango), familiaridad con tecnología (baja/media/alta) y respuestas |
| **Mensajes usados** | **Solo mensajes sintéticos preparados**; nunca mensajes personales reales |

---

## 3. Consentimiento informado (plantilla)

El voluntario debe leer y firmar (o aceptar por escrito) lo siguiente antes de participar:

> **VerifIA — Consentimiento informado (usabilidad)**
>
> 1. He recibido información sobre el propósito de esta prueba: evaluar la usabilidad de un prototipo que analiza mensajes sospechosos de fraude o extorsión.
> 2. Participaré voluntariamente y puedo abandonar la prueba en cualquier momento sin consecuencia.
> 3. No se me pedirán datos personales identificables (nombre, teléfono, correo, dirección, etc.).
> 4. Usaré únicamente mensajes de ejemplo preparados por el equipo; no introduciré mis propios mensajes ni los de otras personas.
> 5. Las respuestas al cuestionario SUS y mis decisiones antes/después de la alerta se registrarán de forma anónima y solo se usarán para este reporte académico.
> 6. El prototipo es **orientativo**: sus alertas no sustituyen el criterio personal ni una denuncia formal ante autoridades.
>
> Firma / aceptación: ____________________    Fecha: ____________

---

## 4. Escenarios preparados (mensajes sintéticos)

Se preparan 10–12 mensajes, cubriendo las 5 tipologías (incluyendo legítimos). Cada participante ve cada mensaje **dos veces**: decide antes de la alerta y después de ver la alerta del sistema.

| # | Mensaje (ejemplo) | Tipología esperada | Decisión correcta antes | Decisión correcta después |
|---|---|---|---|---|
| 1 | "BBVA: cargo de $450 en CAFE CENTRAL. Si no lo reconoces, llama al reverso de tu tarjeta." | legítimo | Ignorar / no actuar | Ignorar / no actuar |
| 2 | "Su cuenta será bloqueada hoy. Confirme su código en [ENLACE:banco-verify.com]" | suplantación bancaria | Actuar con precaución / verificar | No actuar; verificar por canal oficial |
| 3 | "Tu paquete está retenido en aduana. Paga $200 de derecho de entrega hoy." | paquetería retenida | Actuar con precaución / verificar | No actuar; verificar con la paquetería |
| 4 | "Gana $5,000 por semana trabajando desde casa. Paga el entrenamiento para iniciar." | oferta laboral fraudulenta | Actuar con precaución / verificar | No actuar; no pagar anticipado |
| 5 | "Pago o publico tus fotos. Transfiere $3,000 hoy o se las envío a tus contactos." | extorsión | No actuar; denunciar | No actuar; denunciar; no pagar |
| 6 | "Hola Juan, te confirmo la reunión de mañana a las 10:00." | legítimo | Ignorar / no actuar | Ignorar / no actuar |
| 7 | "Citibank: su tarjeta terminación 4821 fue usada en una compra. ¿Fue usted? Responda SÍ/NO." | legítimo | Ignorar / no actuar | Ignorar / no actuar |
| 8 | "Mercado Libre: compra cancelada. Reactívela depositando $500." | paquetería retenida | Actuar con precaución / verificar | No actuar; verificar con Mercado Libre |
| 9 | "Vacante medio tiempo para estudiantes. Sueldo $1,850 semanales. ¿Te interesa?" | oferta laboral (ambigua) | Actuar con precaución | Actuar con precaución / investigar |
| 10 | "Tu adeudo tiene incumplimiento. Actualice sus datos de pago en el portal oficial. Ref: AD-22901." | suplantación (ambigua) | Actuar con precaución | No actuar; verificar con el banco |

> Los mensajes deben mostrarse **ya sanitizados** (con marcadores `[TELEFONO]`, `[ENLACE:dominio.tld]`, etc.), tal como el sistema los presenta al usuario.

---

## 5. Flujo de la prueba (por participante)

1. **Consentimiento** (firma del formulario).
2. **Breve introducción** (2 min): qué es VerifIA, qué hace el semáforo, que es orientativo.
3. **Ronda A — decisión sin alerta:** para cada mensaje, el participante decide qué haría (actuar / ignorar / verificar / denunciar) **sin ver la salida del sistema**. Se registra la decisión.
4. **Ronda B — decisión con alerta:** el participante ve el mismo mensaje con el resultado del sistema (semáforo, tipología, recomendaciones) y decide de nuevo. Se registra la decisión.
5. **Cuestionario SUS:** 10 ítems, escala 1–5 (1 = en total desacuerdo, 5 = totalmente de acuerdo).
6. **Observaciones cualitativas:** el facilitador anota comentarios espontáneos sobre claridad, confusiones, dudas. No se inducen respuestas.
7. **Cierre:** agradecimiento y recordatorio de que el prototipo es orientativo.

Tiempo estimado por participante: 20–30 minutos.

---

## 6. Cuestionario SUS (10 ítems)

| Ítem | Enunciado | Tipo |
|---|---|---|
| 1 | Me gustaría usar este sistema con frecuencia. | Positivo |
| 2 | Lo encontré innecesariamente complejo. | Negativo |
| 3 | Me pareció fácil de usar. | Positivo |
| 4 | Creo que necesitaría apoyo técnico para usarlo. | Negativo |
| 5 | Creo que las funciones están bien integradas. | Positivo |
| 6 | Hubo demasiada inconsistencia. | Negativo |
| 7 | La mayoría de las personas aprendería a usarlo muy rápido. | Positivo |
| 8 | Lo encontré muy engorroso. | Negativo |
| 9 | Me sentí seguro al usarlo. | Positivo |
| 10 | Necesité aprender muchas cosas antes de empezar a usarlo. | Negativo |

**Escala:** 1 = en total desacuerdo … 5 = totalmente de acuerdo.

**Cálculo (Fórmula SUS):**

```python
def sus(respuestas: dict[int, int]) -> float:
    total = 0
    for i in range(1, 11):
        if i % 2 == 1:  # ítems positivos (1, 3, 5, 7, 9)
            total += respuestas[i] - 1
        else:  # ítems negativos (2, 4, 6, 8, 10)
            total += 5 - respuestas[i]
    return total * 2.5   # rango 0–100
```

- Ítems positivos: contribución = puntuación − 1 (0–4)
- Ítems negativos: contribución = 5 − puntuación (0–4)
- SUS = suma de contribuciones × 2,5 → rango 0–100

Referencia descriptiva: **68 es el promedio histórico** (Bangor et al., 2008). Con n = 10–15, el SUS es **descriptivo, no confirmatorio**.

---

## 7. Análisis antes/después de la alerta

Para cada mensaje y participante, se registra si la decisión fue **acertada** (coincide con la decisión correcta esperada) o **no acertada**.

Se construye una tabla de McNemar (medidas repetidas):

| | Acierto después | Fallo después |
|---|---|---|
| **Acierto antes** | a | b |
| **Fallo antes** | c | d |

```python
from statsmodels.stats.contingency_tables import mcnemar
tabla = [[a, b], [c, d]]
resultado = mcnemar(tabla, exact=True)  # exacto por n pequeño
```

**Interpretación con cautela:** con n ≈ 12 solo se detectan efectos grandes. Se reportan proporciones e intervalos de confianza de Wilson, y se evita concluir "no hay efecto" cuando el estudio simplemente carece de potencia.

---

## 8. Reporte de usabilidad

El reporte de validación incluirá:

- n, edad (rangos), familiaridad con tecnología (distribución)
- **SUS: media ± desviación estándar, rango (mín–máx)**
- Tabla de McNemar, valor p exacto, proporciones de acierto antes/después
- Observaciones cualitativas (claridad, confusión, sugerencias)
- Limitación: n pequeño, muestra no probabilística, resultado descriptivo

---

## 9. Plantilla de recolección (una fila por participante)

| id_participante | edad_rango | familiaridad | sus_q1..q10 | sus_total | decision_acertada_antes (n_msgs) | decision_acertada_despues (n_msgs) | observaciones |
|---|---|---|---|---|---|---|---|

> Cada id es un código aleatorio (no nombre ni documento). No se guardan los mensajes vistos ni decisiones texto a texto si pudieran identificar al participante.
