/*
 * I2C logiciel, maître seul, environ 80 kHz.
 *
 * Pourquoi pas le pilote I2C d'ESP-IDF : l'ESP32-C6 n'a qu'un contrôleur I2C
 * rapide, et la carte a deux bus (accéléromètre, port Grove). Surtout, un
 * banc doit dire quelle ligne est en défaut : ce code rend « SDA reste à 0 »
 * ou « SCL reste à 0 » là où un pilote rend un délai dépassé.
 *
 * Les deux broches doivent être en sortie à drain ouvert avec entrée
 * (GPIO_MODE_INPUT_OUTPUT_OD), relâchées. Les rappels sont ceux de la carte.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

typedef struct { int sda, scl; } soft_i2c_t;

#define SOFT_I2C_OK         0
#define SOFT_I2C_NACK       1       /* personne n'a répondu à cette adresse */
#define SOFT_I2C_SDA_LOW    (-1)    /* SDA reste à 0 : pas de rappel, court-circuit ou esclave bloqué */
#define SOFT_I2C_SCL_LOW    (-2)    /* SCL reste à 0 : pas de rappel ou court-circuit */

/* Demande à l'adresse de répondre, sans rien lui écrire. */
int soft_i2c_probe(const soft_i2c_t *bus, uint8_t addr);
/* Écrit un registre. */
int soft_i2c_write_reg(const soft_i2c_t *bus, uint8_t addr, uint8_t reg, uint8_t value);
/* Lit len registres à la suite à partir de reg. */
int soft_i2c_read_regs(const soft_i2c_t *bus, uint8_t addr, uint8_t reg, uint8_t *out, size_t len);
/* Texte d'un code de retour. */
const char *soft_i2c_strerror(int err);
