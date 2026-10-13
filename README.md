# Luciole²

Lumières de vélo qui se parlent. Un essaim de petites unités (M5Stack NanoC6 ou AtomS3 Lite, ruban de LED SK6812) qui se découvrent par radio ESP-NOW longue portée, sans coordinateur ni réseau, et qui montrent d'un coup d'œil si on roule seul ou ensemble. Première sortie : Critical Mass de Bruxelles, 30 octobre 2026, avec les Merveilleux Fous Roulants.

| Dossier | Contenu |
|---|---|
| `firmware/` | Firmware ESP-IDF, une image par puce, nombre de LED en configuration. Voir `firmware/README.md`. |
| `web/` | Page de flashage par USB depuis le navigateur (ESP Web Tools), publiée par GitHub Pages. |
| `sim/` | Simulation d'un Critical Mass : 20 000 vélos, 1 000 lucioles, mêmes règles que le firmware. Un fichier HTML, à ouvrir tel quel. |

Documentation du projet : wiki Outline, collection Luciole² (journal, décisions, architecture et contrat radio, matériel).

## Installer une luciole

Ouvrir la page de flashage dans Chrome ou Edge sur un ordinateur, brancher la luciole en USB, choisir le nombre de LED, cliquer sur Installer. Les mises à jour se font de la même façon.

En local, sans GitHub Pages : compiler (`firmware/README.md`), puis

```bash
python3 web/build.py --local          # assemble web/firmware/ (binaires, configurations NVS, manifestes)
python3 -m http.server 8766 --directory web
```

Web Serial exige HTTPS ou `localhost` : pour flasher depuis un autre poste, il faut passer par la page publiée.

## Faire évoluer le firmware sans casser l'essaim

Le contrat radio v1 (`firmware/main/luciole.h`, section « Contrat radio ») fixe le canal, le mode longue portée, le cycle de 2,5 s et le format des trames. Une luciole déjà distribuée doit rester membre de l'essaim : les nouveaux champs vont en fin de trame, les octets inconnus sont ignorés, la trame d'onde ne se remplace jamais. Le rendu (jauge, couleurs, ondulation) est local et change librement. Vérifier les changements d'échelle dans `sim/index.html` avant de flasher.

## Licence

Luciole² est publié sous [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr) : réutilisation et modification libres avec attribution, partage à l'identique, pas d'usage commercial. Texte complet dans `LICENSE`.
