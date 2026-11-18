/*
 * I2C logiciel : voir soft_i2c.h.
 *
 * Les trois fonctions d'accès aux broches sont les seules qui touchent au
 * matériel. Avec SOFT_I2C_HOST, elles sont fournies par un programme d'essai
 * sur ordinateur, qui simule le bus et un esclave.
 */
#include "soft_i2c.h"

#ifndef SOFT_I2C_HOST
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#define HALF_PERIOD_US 5
static inline void line_set(int gpio, int level) { gpio_set_level(gpio, level); }   /* 1 = relâchée */
static inline int  line_get(int gpio) { return gpio_get_level(gpio); }
static inline void half_period(void) { esp_rom_delay_us(HALF_PERIOD_US); }
#else
void line_set(int gpio, int level);
int  line_get(int gpio);
void half_period(void);
#endif

/* Relâche SCL et attend qu'elle remonte : un esclave peut la retenir, et un
 * rappel faible la fait monter lentement. Au bout d'une milliseconde, la
 * ligne est déclarée tenue à 0. */
static int scl_release(const soft_i2c_t *b)
{
    line_set(b->scl, 1);
    for (int i = 0; i < 200; i++) {
        if (line_get(b->scl)) return SOFT_I2C_OK;
        half_period();
    }
    return SOFT_I2C_SCL_LOW;
}

/* Départ, ou nouveau départ si SCL est à 0 : SDA descend pendant que SCL est haute. */
static int start(const soft_i2c_t *b)
{
    line_set(b->sda, 1);
    half_period();
    int err = scl_release(b);
    if (err) return err;
    half_period();
    if (!line_get(b->sda)) return SOFT_I2C_SDA_LOW;
    line_set(b->sda, 0);
    half_period();
    line_set(b->scl, 0);
    half_period();
    return SOFT_I2C_OK;
}

/* Arrêt : SDA remonte pendant que SCL est haute. Rend les deux lignes relâchées dans tous les cas. */
static void stop(const soft_i2c_t *b)
{
    line_set(b->scl, 0);
    line_set(b->sda, 0);
    half_period();
    scl_release(b);
    half_period();
    line_set(b->sda, 1);
    half_period();
}

/* Envoie un octet, poids fort en tête. Rend SOFT_I2C_OK si l'esclave acquitte. */
static int write_byte(const soft_i2c_t *b, uint8_t value)
{
    int err;
    for (int bit = 7; bit >= 0; bit--) {
        line_set(b->sda, (value >> bit) & 1);
        half_period();
        if ((err = scl_release(b)) != 0) return err;
        half_period();
        line_set(b->scl, 0);
    }
    line_set(b->sda, 1);            /* l'esclave répond sur SDA */
    half_period();
    if ((err = scl_release(b)) != 0) return err;
    half_period();
    int ack = !line_get(b->sda);
    line_set(b->scl, 0);
    half_period();
    return ack ? SOFT_I2C_OK : SOFT_I2C_NACK;
}

/* Lit un octet. ack = 1 pour en demander un autre, 0 pour le dernier. */
static int read_byte(const soft_i2c_t *b, uint8_t *value, int ack)
{
    int err;
    uint8_t v = 0;
    line_set(b->sda, 1);
    for (int bit = 0; bit < 8; bit++) {
        half_period();
        if ((err = scl_release(b)) != 0) return err;
        half_period();
        v = (uint8_t)(v << 1 | (line_get(b->sda) ? 1 : 0));
        line_set(b->scl, 0);
    }
    line_set(b->sda, ack ? 0 : 1);
    half_period();
    if ((err = scl_release(b)) != 0) return err;
    half_period();
    line_set(b->scl, 0);
    line_set(b->sda, 1);
    half_period();
    *value = v;
    return SOFT_I2C_OK;
}

int soft_i2c_probe(const soft_i2c_t *b, uint8_t addr)
{
    int err = start(b);
    if (!err) err = write_byte(b, (uint8_t)(addr << 1));    /* adresse en écriture : rien n'est lu ni écrit */
    stop(b);
    return err;
}

int soft_i2c_write_reg(const soft_i2c_t *b, uint8_t addr, uint8_t reg, uint8_t value)
{
    int err = start(b);
    if (!err) err = write_byte(b, (uint8_t)(addr << 1));
    if (!err) err = write_byte(b, reg);
    if (!err) err = write_byte(b, value);
    stop(b);
    return err;
}

int soft_i2c_read_regs(const soft_i2c_t *b, uint8_t addr, uint8_t reg, uint8_t *out, size_t len)
{
    int err = start(b);
    if (!err) err = write_byte(b, (uint8_t)(addr << 1));
    if (!err) err = write_byte(b, reg);
    if (!err) err = start(b);                               /* nouveau départ, puis adresse en lecture */
    if (!err) err = write_byte(b, (uint8_t)(addr << 1 | 1));
    for (size_t i = 0; !err && i < len; i++) err = read_byte(b, &out[i], i + 1 < len);
    stop(b);
    return err;
}

const char *soft_i2c_strerror(int err)
{
    switch (err) {
        case SOFT_I2C_OK:      return "bon";
        case SOFT_I2C_NACK:    return "pas de reponse";
        case SOFT_I2C_SDA_LOW: return "SDA reste a 0";
        case SOFT_I2C_SCL_LOW: return "SCL reste a 0";
        default:               return "erreur inconnue";
    }
}
