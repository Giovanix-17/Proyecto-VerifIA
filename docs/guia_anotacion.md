# Guía de anotación — VerifIA

Documento operativo de la Fase 2 para asignar **una sola etiqueta** a cada mensaje
del corpus. Fuente de verdad: `VerifIA_memoria_proyecto.md` §8. Si hay conflicto,
gana la memoria.

| Campo | Valor |
|---|---|
| Versión | 1.0 (16/11/2026) |
| Corpus | 500 mensajes, 100 por clase |
| Unidad de anotación | Un mensaje completo (SMS o conversación corta de WhatsApp) |
| Etiqueta a decidir | `tipologia` (una de las 5 clases) |
| Etiqueta que **no** se decide aquí | `nivel_riesgo`: el sistema lo deriva de la puntuación (§8.6) |

---

## 1. Reglas generales

1. **Una etiqueta por mensaje.** No hay etiquetas múltiples ni "otro". Si un
   mensaje combina dos modalidades, se elige la que explique el **pretexto
   principal** (ver §4).
2. **La etiqueta describe el mensaje, no la intención del remitente.** No se
   especula con quién lo envió; se anota lo que el texto permite sostener.
3. **No se anotan datos personales.** El corpus se redacta o genera sin PII real.
   Si aparece un teléfono, correo, CLABE, tarjeta, CURP o RFC que parezca real,
   el mensaje se descarta (no se "arregla" a mano).
4. **No se corrige la redacción** salvo errores evidentes de codificación. Los
   errores ortográficos son señal y se conservan (se anotan como
   `error_ortografico` si son relevantes).
5. **La etiqueta de un mensaje sintético es un borrador.** El autor la confirma
   o la corrige; el borrador queda en `tipologia_borrador` como evidencia.
6. **El conjunto de prueba no se usa para decidir la guía.** Si un caso obliga a
   cambiar una definición, se documenta el cambio y se aplica también a train y
   validación.

---

## 2. Las cinco clases

| Etiqueta interna | Clase de la memoria | Pretexto típico |
|---|---|---|
| `legitimo` | Mensaje legítimo | Aviso, conversación o notificación sin intención de fraude |
| `suplantacion_bancaria` | Suplantación bancaria | Un banco o institución financiera pide datos, códigos o pagos |
| `paqueteria_retenida` | Paquetería retenida | Un envío está retenido y hay que pagar o confirmar datos |
| `oferta_laboral_fraudulenta` | Oferta laboral fraudulenta | Empleo atractivo que exige dinero o datos antes de contratar |
| `extorsion` | Extorsión | Amenaza directa para exigir dinero o silencio |

### 2.1 `legitimo`

**Definición.** Mensaje cotidiano, comercial o institucional que no busca que la
persona entregue dinero, códigos o datos personales a un tercero.

**Señales típicas.** Remitente identificable; información concreta (monto, guía,
fecha, sucursal); invita a usar la app o el canal oficial; no hay amenaza ni
plazo perentorio; si pide "verificar", es dentro de un canal oficial y **no**
solicita códigos ni contraseñas.

**Qué no es.** No es legítimo un mensaje que pide un código aunque se vea
formal; tampoco lo es una notificación bancaria que enlaza a un dominio ajeno o
pide NIP, contraseña o datos completos de tarjeta.

**Ejemplos.**

- `BBVA: Se realizó un cargo de $450.00 en CAFE CENTRAL con tu tarjeta terminación 4821. Si no lo reconoces, llama al número al reverso de tu tarjeta.`
- `DHL: Tu paquete con guía 4720193856 será entregado hoy entre 10:00 y 14:00. No se requiere ningún pago adicional.`
- `Hola mamá, ya llegué a la escuela. Te aviso cuando salga.`
- `IMSS: Tu cita de medicina familiar es el 22 de noviembre a las 9:30 en la Unidad de Parrilla.`
- `BBVA: Tu código de verificación es 837261. Úsalo solo en la app oficial. Nunca lo compartas con terceros.`

**Frontera.** Una notificación real puede pedir "verificar" o avisar de un cargo;
la diferencia es que **no** solicita códigos, NIP, contraseña ni datos completos,
y no empuja a un enlace o teléfono ajeno.

### 2.2 `suplantacion_bancaria`

**Definición.** Mensaje que se hace pasar por un banco, tarjeta, banca en línea o
institución financiera para obtener credenciales, códigos, datos de tarjeta o un
pago "de verificación".

**Señales típicas.** Suplantación de marca; urgencia ("hoy", "24 horas");
amenaza de bloqueo, cancelación o embargo; solicitud de NIP, contraseña, token,
OTP, CVV, CLABE o datos completos; enlace a dominio que imita al banco; premio o
reembolso condicionado; instrucción de transferir a una "cuenta segura".

**Qué no es.** No es suplantación bancaria una amenaza directa a la persona sin
pretexto financiero (eso es extorsión), ni un aviso legítimo que solo informa un
cargo y remite al canal oficial.

**Ejemplos.**

- `BBVA: Detectamos un cargo de $8,750 en tu tarjeta. Confirma si lo reconoces aquí: bbva-validacion-segura.com`
- `Su tarjeta Banorte fue bloqueada por seguridad. Para desbloquearla envíe el código de 6 dígitos que recibirá por SMS.`
- `Le llamamos del departamento de fraudes. No cuelgue. Necesitamos que nos dicte el código que acaba de recibir.`
- `Santander le informa que tiene un reembolso de $2,300 pendiente. Ingrese su CLABE para recibirlo.`
- `Su cuenta fue marcada por lavado de dinero. Para aclararlo, deposite $3,000 en la cuenta de verificación.`

**Frontera con extorsión.** Si el mensaje **suplanta a una institución** y pide
credenciales, códigos o un pago de verificación, es suplantación bancaria. Si
**amenaza a la persona** (familiar, fotos, integridad, negocio) para exigir
dinero, es extorsión, aunque mencione un banco o una deuda.

### 2.3 `paqueteria_retenida`

**Definición.** Mensaje que se hace pasar por una paquetería o aduana para
cobrar un "derecho de entrega", "impuesto" o "reprogramación" y obtener datos o
dinero.

**Señales típicas.** Suplantación de paquetería; paquete retenido, dirección
incompleta o intento fallido; pago pequeño y urgente; enlace de rastreo falso;
plazo de 24–48 horas y amenaza de devolución; solicitud de INE, RFC o tarjeta.

**Qué no es.** No es paquetería una oferta de empleo con pretexto de logística,
ni un aviso legítimo de entrega que no pide pago ni datos.

**Ejemplos.**

- `DHL: Su paquete está retenido en aduana. Pague $320 de impuestos en dhl-pago-mx.com para liberarlo hoy.`
- `Amazon: Tu pedido no pudo entregarse porque la dirección está incompleta. Actualízala aquí: amazon-entrega.net.`
- `Mercado Libre: Tu paquete será devuelto si no pagas $199 de derecho de entrega antes de las 6 pm.`
- `FedEx: Su envío requiere pago de impuesto aduanal de $1,250. Deposite en la cuenta 0000 0000 0000 0000.`
- `Estafeta: Su paquete será subastado si no paga el almacenaje hoy. Llame al 55 0000 0000.`

**Frontera con oferta laboral.** Ambas usan enlaces y urgencia. Manda el
**pretexto**: si el mensaje gira en torno a un envío retenido, es paquetería; si
gira en torno a un empleo, es oferta laboral.

### 2.4 `oferta_laboral_fraudulenta`

**Definición.** Mensaje que ofrece un empleo atractivo y, antes de contratar,
pide dinero (uniforme, material, capacitación, examen) o datos personales y
bancarios.

**Señales típicas.** Sueldo alto sin experiencia; contratación inmediata; trabajo
desde casa por WhatsApp; pago por adelantado; solicitud de CLABE, INE, CURP, RFC
o foto de tarjeta; enlace a formulario; comisiones por reclutar; "últimos
lugares".

**Qué no es.** No es oferta fraudulenta una vacante real que no cobra y que
canaliza el proceso por el sitio oficial de la empresa.

**Ejemplos.**

- `¡Hola! Buscamos personas para trabajar desde casa. $800 diarios, sin experiencia. Manda WhatsApp al 55 0000 0000.`
- `Reclutador: Tu perfil fue seleccionado. Solo paga $350 de capacitación y empiezas mañana.`
- `Hola, somos de una empresa de logística. Necesitamos tu CLABE para depositarte el sueldo antes de firmar contrato.`
- `Empleo garantizado en Canadá. Paga $5,000 de gestoría y te damos la carta de oferta.`
- `Trabaja reclutando gente desde tu celular. Ganas $500 por cada persona que se una.`

**Frontera con paquetería.** Si el gancho es "trabaja empacando pedidos" y el
pago solicitado es por material o capacitación, es oferta laboral; si el gancho
es "tu paquete está retenido", es paquetería.

### 2.5 `extorsion`

**Definición.** Mensaje que amenaza a la persona (o a un familiar) para exigir
dinero, silencio o una acción inmediata.

**Señales típicas.** Amenaza explícita o velada; plazo corto; prohibición de
avisar; familiar secuestrado o detenido; fotos o conversaciones; cobro de piso;
deuda inventada; supuesta denuncia o citatorio; lenguaje intimidante.

**Qué no es.** No es extorsión una simple cobranza legítima que informa un
adeudo y ofrece canales de pago, ni una suplantación bancaria que solo pide
credenciales sin amenazar a la persona.

**Ejemplos.**

- `Te tenemos ubicado. Si no depositas $5,000 hoy, le mandamos esto a tu familia.`
- `Hablamos de parte de un grupo. Tu familiar está con nosotros. Paga $10,000 si quieres que regrese.`
- `Tenemos fotos tuyas. Transfiere $3,000 o las publicamos en tus contactos.`
- `Soy de un grupo de la zona. Tu negocio necesita pagar piso: $1,500 semanales.`
- `Somos de la fiscalía. Hay una orden de aprehensión contra ti. Deposita $7,000 para arreglarlo.`

**Frontera con suplantación bancaria.** La extorsión **amenaza a la persona**;
la suplantación bancaria **suplanta a la institución** y pide credenciales o un
pago de verificación. Si hay ambas, pesa la amenaza directa → extorsión.

---

## 3. Catálogo de señales

| Señal | Definición operativa |
|---|---|
| `urgencia` | Plazo corto, "hoy", "24 horas", "último aviso", presión para actuar ya. |
| `amenaza` | Consecuencia negativa explícita: bloqueo, embargo, daño, publicación, detención. |
| `suplantacion` | Se atribuye la identidad de un banco, paquetería, institución o autoridad. |
| `solicitud_datos` | Pide NIP, contraseña, CLABE, tarjeta, CURP, RFC, INE, dirección o similar. |
| `solicitud_codigo` | Pide un código, token, OTP, PIN o NIP concreto para "verificar" o "desbloquear". |
| `enlace_sospechoso` | Enlace a dominio que imita una marca, acortador o dominio ajeno al oficial. |
| `pago_anticipado` | Exige dinero antes de entregar un bien, servicio, empleo o premio. |
| `premio_falso` | Anuncia un premio, reembolso o beneficio condicionado a pagar o dar datos. |
| `error_ortografico` | Errores evidentes que sugieren un mensaje masivo o apócrifo. |

Una señal se marca solo si el texto la sostiene; no se infiere por el tipo de
mensaje. Se permiten de 1 a 4 señales por mensaje (lo habitual es 1–3).

---

## 4. Orden de decisión para casos ambiguos

1. ¿Hay **amenaza directa a la persona** (o a un familiar) para exigir dinero o
   silencio? → `extorsion`.
2. ¿Se **suplanta a un banco o institución financiera** y se piden credenciales,
   códigos o un pago de verificación? → `suplantacion_bancaria`.
3. ¿El pretexto es un **envío retenido** y se pide pago o datos? →
   `paqueteria_retenida`.
4. ¿El pretexto es un **empleo** y se pide dinero o datos antes de contratar? →
   `oferta_laboral_fraudulenta`.
5. Si no hay amenaza, suplantación, cobro anticipado ni solicitud de datos
   sensibles → `legitimo`.

Casos que suelen fallar:

- **"Su paquete será devuelto si no paga"**: la devolución es una consecuencia,
  no una amenaza a la persona → paquetería.
- **"Somos de la fiscalía, pague para evitar la orden de aprehensión"**: hay
  suplantación de autoridad y amenaza de detención → extorsión.
- **"Su cuenta será bloqueada, confirme su NIP"**: suplantación bancaria, no
  extorsión, porque el daño es al servicio y se piden credenciales.
- **"Tu currículum fue seleccionado, deposita $600"**: oferta laboral, no
  suplantación bancaria, aunque pida una cuenta.
- **Notificación real de banco que dice "verifica en la app"**: legítimo; no
  pide códigos y no enlaza a un dominio ajeno.

---

## 5. Procedimiento de revisión del corpus

1. Ejecutar `python scripts/corpus_review.py --export` para generar
   `data/annotated/revision.csv` (una fila por mensaje).
2. Revisar, en este orden:
   - mensajes con `origen = sintetico_llm` (borrador del LLM);
   - mensajes con `senales_alerta` vacías;
   - una muestra del 20 % estratificado del resto.
3. En el CSV:
   - `confirmar = si` si la etiqueta es correcta;
   - `tipologia_corregida` si hay que cambiarla;
   - `senales_corregidas` separadas por `;` si hay que ajustarlas;
   - `nota` para explicar un caso ambiguo.
4. Ejecutar `python scripts/corpus_review.py --import` y después
   `python scripts/corpus_build.py` para regenerar splits y manifiesto.
5. Los desacuerdos sistemáticos se anotan en esta guía y se aplican a todo el
   corpus (no caso por caso).

La revisión deja `revision_autor = confirmado` en los mensajes revisados. El
reporte de cobertura muestra cuántos quedan pendientes.

---

## 6. Registro de cambios

| Fecha | Cambio | Motivo |
|---|---|---|
| 16/11/2026 | Versión inicial | Fase 2 del proyecto |
