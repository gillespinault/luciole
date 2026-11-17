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
| `Espressif_ESP32-C6_puce_datasheet_v1.6.pdf` | Fiche de la puce. État des broches au reset, tableau 2-2 ; broches de démarrage, chapitre 3 | https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf | 17 novembre 2026 |
| `Espressif_ESP32-C6_hardware_design_guidelines_2026-11-12.pdf` | Consignes de conception d'Espressif : EN et superviseur, USB, antenne | https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/esp-hardware-design-guidelines-en-master-esp32c6.pdf | 17 novembre 2026 |
| `Espressif_ESP32-C6_technical_reference_manual_v1.2.pdf` | Manuel de référence : configuration des broches après reset, réveil, maintien en sommeil | https://www.espressif.com/sites/default/files/documentation/esp32-c6_technical_reference_manual_en.pdf | 17 novembre 2026 |
| `TopPower_TP4056_rev2.4_LCSC-C16581.pdf` | Chargeur TP4056, LCSC C16581, révision 2.4 : courant = 1 100 / R, seuils de température, brochage | https://datasheet.lcsc.com/datasheet/pdf/d328ee101cbb1f3719611cd61db479c2.pdf | 17 novembre 2026 |
| `TI_SN74AHCT1G125_SCLS378P.pdf` | Tampon comparé et écarté : 4,5 V au moins d'alimentation | https://www.ti.com/lit/ds/symlink/sn74ahct1g125.pdf | 17 novembre 2026 |

## Composants de la carte v0

Fiches relevées le 17 novembre 2026 par l'API de LCSC, pour choisir les composants. Le nom du fichier finit par la référence LCSC.

| Fichier | Contenu | Source |
|---------|---------|--------|
| `Richtek_RT9080_C841192.pdf` | Régulateur 3,3 V RT9080-33GJ5, LCSC C841192, fiche DS9080-05. Brochage page 2, tableau électrique page 4 | https://datasheet.lcsc.com/datasheet/pdf/2701e0c3a2b84b9965f7a61f2c14e970.pdf |
| `PUOLOP_DW01A_C351410.pdf` | Protection de cellule DW01A, LCSC C351410. Brochage et seuils pages 1 à 3 | https://datasheet.lcsc.com/datasheet/pdf/0d2b2b5e8d1207bf276387cb4ff3a495.pdf |
| `TechPublic_FS8205A_C2830320.pdf` | Double transistor N de la protection, LCSC C2830320. Fiche en image : brochage page 1 | https://datasheet.lcsc.com/datasheet/pdf/c060cb7baa8cc2b2d2a0ed3afa443ef8.pdf |
| `Diodes_DMP1045U_C177033.pdf` | Transistor P à faible résistance, LCSC C177033 : 45 mΩ au plus à 2,5 V de commande | https://datasheet.lcsc.com/datasheet/pdf/a415ca01cfb9427ebaa1d0897b522cb1.pdf |
| `AOS_AO3401A_C15127.pdf` | Transistor P de base chez JLCPCB, comparé et écarté : 85 mΩ au plus à 2,5 V | https://datasheet.lcsc.com/datasheet/pdf/fee353dd1e9e0bc90b295f14f381aa4c.pdf |
| `Vishay_SI2333CDS_C144846.pdf` | Transistor P comparé : 45 mΩ au plus à 2,5 V | https://datasheet.lcsc.com/datasheet/pdf/6341b2d7c29f4f6893ce2e6a167fc9bc.pdf |
| `Diodes_DMG2305UX_C144153.pdf` | Transistor P comparé et écarté : 100 mΩ au plus à 2,5 V | https://datasheet.lcsc.com/datasheet/pdf/47e4eca1ed8982a4ce6cf0c3e9eb9c9f.pdf |
| `SI2333DDS_C5122041.pdf` | Transistor P comparé (Tech Public). Fiche en image, non exploitée | https://datasheet.lcsc.com/datasheet/pdf/d5092adcd1bd35a719b099d8e299b4c4.pdf |
| `AOS_AO3400A_C20917.pdf` | Transistor N de commande, LCSC C20917 : seuil de 0,65 à 1,45 V | https://datasheet.lcsc.com/datasheet/pdf/130876b936da464599428c58fd8de8f6.pdf |
| `ST_LIS2DH12_C110926.pdf` | Accéléromètre LIS2DH12TR, LCSC C110926. Brochage table 2, consommation table 4 | https://datasheet.lcsc.com/datasheet/pdf/80fd3cb5c04ce9b30e9bec7b53c4a455.pdf |
| `Silan_SC7A20H_C19274408.pdf` | Accéléromètre SC7A20H, candidat moins cher. Fiche en chinois ; son brochage ne semble pas celui du LIS2DH12, à vérifier avant tout usage | https://datasheet.lcsc.com/datasheet/pdf/e1b1e152d7887428b14d4f559181a1af.pdf |
| `ST_LIS2DW12_C189624.pdf` | Accéléromètre LIS2DW12, comparé, non retenu | https://datasheet.lcsc.com/datasheet/pdf/faa0f1ff935ff2be849a090ec963fd19.pdf |
| `HRO_TYPE-C-31-M-12_C165948.pdf` | Connecteur USB-C 16 contacts, LCSC C165948. Plan sur une page | https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf |
| `A2001WR-S-2P_C225233.pdf` | Connecteur de batterie au pas de 2 mm, couché, CJT A2001WR-S-2P, LCSC C225233. Remplace le JST S2B-PH-SM4-TB, en rupture chez LCSC le 17 novembre | https://datasheet.lcsc.com/datasheet/pdf/d9fc725fe9fc8ec7da185e87bd3dbbda.pdf |
| `Murata_NCP15XH103F03RC_C77131.pdf` | Thermistance 10 kΩ, B 3380, LCSC C77131. Catalogue : table résistance-température de la série XH103 | https://datasheet.lcsc.com/datasheet/pdf/c9e5c9a36e405340079034c7608ac4b6.pdf |
| `TI_SN74LV1T34_C100024.pdf` | Tampon de niveau SN74LV1T34DBVR, LCSC C100024 : seuil haut d'entrée de 2,0 V sous 5 V | https://datasheet.lcsc.com/datasheet/pdf/ffee958492a142ea9562c7ea937e2508.pdf |
| `SMD1206B075TF-16_C269118.pdf` | Fusible réarmable 0,75 A de maintien, 1,5 A de déclenchement, 16 V, LCSC C269118 | https://datasheet.lcsc.com/datasheet/pdf/8a605baeacdab5535f2f8f2e17661456.pdf |
| `ST_USBLC6-2SC6_C7519.pdf` | Protection des lignes USB, LCSC C7519 | https://datasheet.lcsc.com/datasheet/pdf/0d3a2ab954b34651a0695e7ccf534db0.pdf |
| `Nexperia_PESD5Z5.0_C132368.pdf` | Diode de protection 5 V pour le port Grove et le bouton, LCSC C132368 : 1 cathode, 2 anode | https://datasheet.lcsc.com/datasheet/pdf/f0b6449e8467793d14f077806a021ac5.pdf |
| `XUNPU_TS-1088-AR02016_C720477.pdf` | Bouton interne (flashage, redémarrage), LCSC C720477, pièce de base | https://datasheet.lcsc.com/datasheet/pdf/0475ac02febf455ca9ddcfb380b0df0d.pdf |
| `Alps_SKRTLAE010_C110293.pdf` | Bouton utilisateur à poussée latérale, LCSC C110293 | https://datasheet.lcsc.com/datasheet/pdf/776a4001117146b9aca9bcb4d41038c0.pdf |
| `SHOUHAN_TS24CA_C393942.pdf` | Bouton latéral comparé, non retenu : 20 000 cycles | https://datasheet.lcsc.com/datasheet/pdf/18e10a18b694191d090bf9cd1261c089.pdf |
| `Murata_DFE252010F-1R0M_C470857.pdf` | Inductance 1 µH comparée et écartée : saturation à 4,1 A | https://datasheet.lcsc.com/datasheet/pdf/549844e8a6086594e60060064c73b05e.pdf |
| `MDD_SS14_C2480.pdf` | Diode Schottky 1 A comparée et écartée, trop juste en courant, LCSC C2480 | https://datasheet.lcsc.com/datasheet/pdf/9977bb85cd7e349115b7bcb7054cfa0d.pdf |
| `JSCJ_B5819W_C8598.pdf` | Diode Schottky comparée, pièce de base, LCSC C8598 | https://datasheet.lcsc.com/datasheet/pdf/4ac2c059be7c462694ab0715ce987a85.pdf |
| `DSK24_C22466352.pdf` | Diode Schottky 2 A du partage de charge, retenue, LCSC C22466352 | https://datasheet.lcsc.com/datasheet/pdf/9bfcfb61be82dd0a0795b8336c9e8faf.pdf |
| `cjiang_FXL0420-1R5-M_C167205.pdf` | Catalogue des inductances FXL. La FXL0420-1R0-M retenue (LCSC C167203) y figure : 1 µH, 27 mΩ, saturation à 5,6 A | https://datasheet.lcsc.com/datasheet/pdf/cdeaf11c37761d852f97ebb5746bffdf.pdf |
| `TI_TLV803E_C5218924.pdf` | Superviseur de tension TLV803EA30DBZR, LCSC C5218924 : 3,08 V, drain ouvert. Attention, deux brochages selon le suffixe | https://datasheet.lcsc.com/datasheet/pdf/075232f81476471fb0145392049399fa.pdf |
| `Torex_XC61C_C2456348.pdf` | Superviseur comparé, non retenu | https://datasheet.lcsc.com/datasheet/pdf/e118bf1ce5f64ee80f5f033c5227a646.pdf |
| `BAT54C_C37704.pdf` | Double diode Schottky à cathode commune, LCSC C37704 : 1 et 2 anodes, 3 cathode | https://datasheet.lcsc.com/datasheet/pdf/753e903e66757b8dda706efd5e61ce1e.pdf |
| `TechPublic_SN74LV1T125_C51886115.pdf` | Tampon à trois états du port, à l'essai sur le premier lot, LCSC C51886115. Fiche en image | https://datasheet.lcsc.com/datasheet/pdf/d61badc48b1e3ef9b419e747e22ee65f.pdf |

## Preuves du brochage du Grove

Dans `grove-preuves/`. Elles établissent que, connecteur couché vu de dessus et ouverture vers soi, on lit de gauche à droite 4 masse, 3 alimentation, 2 SDA, 1 SCL. Le raisonnement est en tête de l'empreinte, dans `lib/build_lib.py`.

| Fichier | Ce qu'il montre | Source |
|---------|-----------------|--------|
| `M5Stack_A099_dessus.png`, `M5Stack_A099_dessous.png` | Adaptateur « Grove to 4PIN ». La sérigraphie du dos lit signal, signal, 5V, GND ; la pastille carrée est à droite dans les deux vues | https://docs.m5stack.com/en/accessory/converter/grove_to_4p |
| `M5Stack_NanoC6_photo1.png`, `photo4`, `photo5`, `photo8` | NanoC6 : légende côté bouton, vue de dessus, étiquette du dessous, vue dans l'ouverture | https://docs.m5stack.com/en/core/M5NanoC6 |
| `M5Stack_cable_Grove.jpg` | Câble M5Stack : fils noir, rouge, jaune, blanc dans cet ordre | https://docs.m5stack.com/en/accessory/cable/grove_cable |
| `Seeed_OPL_GROVE-HW4-SMD-2.0-90D.kicad_mod` | Empreinte officielle de Seeed, même numérotation que la nôtre une fois tournée | https://github.com/Seeed-Studio/OPL_Kicad_Library |
