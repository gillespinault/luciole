# Fiches techniques et pièces de preuve

Les documents des fabricants sur lesquels reposent les empreintes et les choix de la carte. Ils ne sont pas suivis par git : le dépôt est public et ces fichiers appartiennent à leurs auteurs. Cette liste, elle, est suivie, pour pouvoir les retrouver.

Quand une cote ou un brochage vient d'une fiche, c'est cette révision qui fait foi. Une révision plus récente se compare à celle-ci avant de la remplacer.

| Fichier | Contenu | Source | Relevé le |
|---------|---------|--------|-----------|
| `OPSCO_SK6812MINI-B-012_revB1_2025-09-01.pdf` | LED de la carte, LCSC C5183448, révision B/1. Brochage et pastilles page 5, limites électriques page 6 | https://datasheet.lcsc.com/datasheet/pdf/548befcadb2d78c7835f9363d2f11b5b.pdf | 17 novembre 2026 |
| `Megastar_ZX-HY2.0-4PWT.pdf` | Connecteur Grove couché, LCSC C7429571. Le plan ne numérote pas les broches | https://datasheet.lcsc.com/datasheet/pdf/e46d54a94fecda2645bf71cedac5ff20.pdf | 17 novembre 2026 |
| `TI_TPS61023_SLVSF14B_revB.pdf` | Convertisseur élévateur du rail des LED, LCSC C919459 | https://www.ti.com/lit/ds/symlink/tps61023.pdf | 17 novembre 2026 |
| `Espressif_ESP32-C6-MINI-1_datasheet.pdf` | Module radio. Table des contacts 3-1, broches de démarrage chapitre 4 | https://www.espressif.com/sites/default/files/documentation/esp32-c6-mini-1_mini-1u_datasheet_en.pdf | 17 novembre 2026 |
| `M5Stack_NanoC6_schema_v0.0.1.pdf` | Schéma du NanoC6. Numérotation du port Grove : 1 GPIO1, 2 GPIO2, 3 5 V, 4 masse | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/505/Sch_M5NanoC6_v0.0.1.pdf | 17 novembre 2026 |
| `Seeed_Grove_90D_SMD_plan.pdf` | Plan du connecteur Grove couché vendu par Seeed. Autres cotes que le Megastar | https://core-electronics.com.au/attachments/localcontent/GroveFemaleHeader-SMD-4P-2_219784ee67f.pdf | 17 novembre 2026 |

## Preuves du brochage du Grove

Dans `grove-preuves/`. Elles établissent que, connecteur couché vu de dessus et ouverture vers soi, on lit de gauche à droite 4 masse, 3 alimentation, 2 SDA, 1 SCL. Le raisonnement est en tête de l'empreinte, dans `lib/build_lib.py`.

| Fichier | Ce qu'il montre | Source |
|---------|-----------------|--------|
| `M5Stack_A099_dessus.png`, `M5Stack_A099_dessous.png` | Adaptateur « Grove to 4PIN ». La sérigraphie du dos lit signal, signal, 5V, GND ; la pastille carrée est à droite dans les deux vues | https://docs.m5stack.com/en/accessory/converter/grove_to_4p |
| `M5Stack_NanoC6_photo1.png`, `photo4`, `photo5`, `photo8` | NanoC6 : légende côté bouton, vue de dessus, étiquette du dessous, vue dans l'ouverture | https://docs.m5stack.com/en/core/M5NanoC6 |
| `M5Stack_cable_Grove.jpg` | Câble M5Stack : fils noir, rouge, jaune, blanc dans cet ordre | https://docs.m5stack.com/en/accessory/cable/grove_cable |
| `Seeed_OPL_GROVE-HW4-SMD-2.0-90D.kicad_mod` | Empreinte officielle de Seeed, même numérotation que la nôtre une fois tournée | https://github.com/Seeed-Studio/OPL_Kicad_Library |
