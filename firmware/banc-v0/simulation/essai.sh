#!/bin/sh
# Déroule les commandes du banc sur l'ordinateur, contre une carte simulée
# (carte.c : modèle des broches d'après circuit.py, accéléromètre simulé).
#
#   simulation/essai.sh              tous les scénarios, une ligne de bilan chacun
#   simulation/essai.sh tout         un scénario, avec toute la console
#
# Un scénario est un fichier de scenarios/ : une commande du banc par ligne,
# « @scenario nom » pour une panne simulée, « @attend ms » pour laisser tourner
# une animation, « # attendu : texte » pour un texte qui doit paraître.
# La simulation vérifie d'elle-même des règles et s'arrête en erreur sinon :
#  - rien n'est commandé avant la première commande, CHG_INH n'est jamais
#    poussée à 1, les broches de l'USB ne sont jamais touchées, aucune LED ne
#    dépasse le plafond ;
#  - port Grove (schéma 0.6) : PORT_PU, IO1 et IO2 à 0 tant que le convertisseur
#    est arrêté, PORT_PU commandée avant BOOST_EN et jamais en l'air, trame du
#    ruban envoyée deux fois ;
#  - la batterie et la ligne CC sont lues avec l'atténuation de 2,5 dB.
# Elle ne dit rien des pilotes réels d'ESP-IDF ni de l'électronique.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Faux en-têtes ESP-IDF : chacun renvoie à faux_idf.h.
for h in freertos/FreeRTOS.h freertos/task.h freertos/semphr.h esp_log.h esp_err.h esp_timer.h esp_system.h \
         esp_mac.h esp_cpu.h esp_rom_sys.h esp_chip_info.h esp_flash.h esp_wifi.h esp_now.h esp_event.h esp_netif.h \
         esp_adc/adc_oneshot.h esp_adc/adc_cali.h esp_adc/adc_cali_scheme.h driver/gpio.h driver/uart.h \
         driver/usb_serial_jtag.h driver/usb_serial_jtag_vfs.h driver/temperature_sensor.h soc/soc.h soc/gpio_reg.h \
         soc/uart_pins.h led_strip.h; do
    mkdir -p "$tmp/inc/$(dirname "$h")"
    echo '#include "faux_idf.h"' > "$tmp/inc/$h"
done
gcc -std=gnu17 -Wall -Wextra -Wshadow -Wno-unused-parameter -g -fsanitize=address,undefined \
    -I"$tmp/inc" -I"$here" -I"$here/../main" \
    "$here/../main/main.c" "$here/../main/soft_i2c.c" "$here/carte.c" -lm -o "$tmp/banc"

if [ $# -ge 1 ]; then
    "$tmp/banc" "$here/scenarios/$1.txt"
    exit $?
fi

failed=0
for f in "$here"/scenarios/*.txt; do
    name=$(basename "$f" .txt)
    status=bon
    "$tmp/banc" "$f" > "$tmp/out" 2>&1 || status="ERREUR (regle violee ou plantage)"
    grep '^# attendu : ' "$f" | sed 's/^# attendu : //' > "$tmp/expected" || true
    while IFS= read -r want; do
        grep -qF -- "$want" "$tmp/out" || { status="ERREUR (texte absent : $want)"; }
    done < "$tmp/expected"
    [ "$status" = bon ] || failed=1
    printf '%-20s %s\n' "$name" "$status"
done
exit $failed
