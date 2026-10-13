#!/usr/bin/env python3
"""Assemble le dossier web/firmware/ pour la page de flashage (ESP Web Tools).

  python3 web/build.py --local    # prend firmware/build (C6) et firmware/build-esp32s3 (S3)
  python3 web/build.py            # suppose les binaires déjà copiés dans web/firmware/<cible>/ (CI)

Produit : web/simulation/index.html (copie de sim/index.html),
          web/firmware/nvs/leds-N.bin (configuration : nombre de LED),
          web/firmware/manifest-N.json (un par nombre de LED, toutes les cartes),
          web/firmware/index.json (liste des choix, version, pour la page).

Génération NVS : paquet pip `esp-idf-nvs-partition-gen` (fourni par ESP-IDF, ou `pip install`).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web", "firmware")
HDR = os.path.join(ROOT, "firmware", "main", "luciole.h")
PARTS = os.path.join(ROOT, "firmware", "partitions.csv")

TARGETS = {  # cible IDF -> famille de puce ESP Web Tools, dossier de build local
    "esp32c6": ("ESP32-C6", "build"),
    "esp32s3": ("ESP32-S3", "build-esp32s3"),
}
BOOTLOADER_OFFSET = 0x0   # C6 et S3 : 0x0 (l'ESP32 classique serait 0x1000)
TABLE_OFFSET = 0x8000
APP_OFFSET = 0x10000


def header_value(name, pattern):
    src = open(HDR, encoding="utf-8").read()
    m = re.search(r"#define\s+%s\s+%s" % (name, pattern), src)
    if not m:
        sys.exit("%s introuvable dans luciole.h" % name)
    return m.group(1)


def nvs_partition():
    for line in open(PARTS, encoding="utf-8"):
        f = [x.strip() for x in line.split(",")]
        if len(f) >= 5 and f[1] == "data" and f[2] == "nvs":
            return int(f[3], 0), int(f[4], 0)
    sys.exit("partition nvs introuvable dans partitions.csv")


def gen_nvs(leds, size, out):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("key,type,encoding,value\n")
        f.write("%s,namespace,,\n" % header_value("L2_NVS_NAMESPACE", r'"([^"]+)"'))
        f.write("%s,data,u16,%d\n" % (header_value("L2_NVS_KEY_LEDS", r'"([^"]+)"'), leds))
        csv = f.name
    try:
        subprocess.run([sys.executable, "-m", "esp_idf_nvs_partition_gen.nvs_partition_gen", "generate", csv, out, "0x%x" % size],
                       check=True, stdout=subprocess.DEVNULL)
    finally:
        os.unlink(csv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="copier depuis firmware/build*")
    ap.add_argument("--repo", default="", help="URL du dépôt, affichée sur la page")
    a = ap.parse_args()

    version = header_value("L2_FW_VERSION", r'"([^"]+)"')
    protocol = int(header_value("L2_PROTO_VERSION", r"(\d+)"))
    default_leds = int(header_value("L2_STRIP_LEDS_DEFAULT", r"(\d+)"))
    max_leds = int(header_value("L2_STRIP_LEDS_MAX", r"(\d+)"))
    leds = list(range(1, max_leds + 1))
    nvs_off, nvs_size = nvs_partition()

    if a.local:
        for target, (_, bdir) in TARGETS.items():
            src = os.path.join(ROOT, "firmware", bdir)
            if not os.path.exists(os.path.join(src, "luciole.bin")):
                print("pas de build pour %s (%s), ignoré" % (target, src)); continue
            dst = os.path.join(WEB, target); os.makedirs(dst, exist_ok=True)
            shutil.copy(os.path.join(src, "bootloader", "bootloader.bin"), dst)
            shutil.copy(os.path.join(src, "partition_table", "partition-table.bin"), dst)
            shutil.copy(os.path.join(src, "luciole.bin"), dst)

    sim_dst = os.path.join(ROOT, "web", "simulation"); os.makedirs(sim_dst, exist_ok=True)
    shutil.copy(os.path.join(ROOT, "sim", "index.html"), os.path.join(sim_dst, "index.html"))

    present = [t for t in TARGETS if os.path.exists(os.path.join(WEB, t, "luciole.bin"))]
    if not present:
        sys.exit("aucun binaire dans %s" % WEB)
    os.makedirs(os.path.join(WEB, "nvs"), exist_ok=True)
    for n in leds:
        gen_nvs(n, nvs_size, os.path.join(WEB, "nvs", "leds-%d.bin" % n))
        manifest = {
            "name": "Luciole²", "version": version, "new_install_prompt_erase": True,
            "builds": [{
                "chipFamily": TARGETS[t][0],
                "parts": [
                    {"path": "%s/bootloader.bin" % t, "offset": BOOTLOADER_OFFSET},
                    {"path": "%s/partition-table.bin" % t, "offset": TABLE_OFFSET},
                    {"path": "nvs/leds-%d.bin" % n, "offset": nvs_off},
                    {"path": "%s/luciole.bin" % t, "offset": APP_OFFSET},
                ]} for t in present],
        }
        json.dump(manifest, open(os.path.join(WEB, "manifest-%d.json" % n), "w"), ensure_ascii=False, indent=1)
    json.dump({"version": version, "protocol": protocol, "min": 1, "max": max_leds, "default": default_leds, "targets": present, "repo": a.repo},
              open(os.path.join(WEB, "index.json"), "w"), ensure_ascii=False, indent=1)
    print("web/firmware : fw %s, protocole %d, cibles %s, %d choix de LED" % (version, protocol, ", ".join(present), len(leds)))


if __name__ == "__main__":
    main()
