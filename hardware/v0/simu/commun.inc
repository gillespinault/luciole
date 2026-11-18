* Luciole² v0, révision 0.5 : étage d'alimentation, d'après v0/circuit.py et
* v0/netlist_voulue.txt. Fichier inclus par tous les cas ; les noms de nœuds
* sont ceux des réseaux du schéma, en minuscules. Le nœud 0 est GND, la masse
* de la carte. BATN est le pôle négatif de la batterie, en amont de Q3.
*
* Ce qu'un cas peut changer depuis son bloc .control :
*   alter Vcell dc = 3.7        tension de la cellule ; négative = cellule à l'envers
*   alter Vctl_cell dc = 0      cellule débranchée (1 : branchée)
*   alter Vctl_usb dc = 0       câble USB débranché (1 : branché)
*   alter Vctl_q3 dc = 0        protection de cellule ouverte : diodes de corps de Q3
*                               seules (1 : Q3 passant)
*   alter Vusb dc = 5           tension de la source USB
*   alter Vctl_isys dc = 1      courant tiré sur VSYS, en ampères
*   alter Vctl_ibat dc = 1      courant tiré directement sur VBAT, en ampères
*   alter Ifuite dc = 0.2m      fuite inverse ajoutée à D16 (de VSYS vers VBUS)
*   alter Vtth dc = 25          température de la thermistance, en °C
*   alter Vinh dc = 0, alter Rinh = 30     état de GPIO21 (CHG_INH)
*   alter Viset dc = 3.3, alter Riset = 30 état de GPIO14 (ISET)
*   alterparam nom = valeur, puis reset    tout paramètre ci-dessous
* Les ponts JP1, JP2 et JP3 sont fermés : VCHG = VBAT, V3IN = VBIN = VSYS.

.param r43=10k r45=1Meg r46=10k
.param r5=470 r6=1k
.param r44=100k r47=4.7k
.param r8=2.7k r9=2.2k
.param r11=5.6k r12=200k rth25=10k bth=3380
* DW01A : auto=0, Q3 suit la commande Vctl_q3 ; auto=1, comportement d'après la
* tension vue par la puce (plusieurs points de repos : réservé aux essais)
.param auto=0
* décalage des seuils (0 : modèle du fabricant tel quel)
.param dvto_q2=0 dvto_q6=0 dvto_q4=0
* cellule : résistance totale (cellule, protection du pack, fils, contacts) et
* inductance des fils
.param rcell=0.1 lcell=50n
* câble USB et contacts
.param rusb=0.2
* essai de correction, absent du schéma : condensateur entre la grille de Q2 et
* BATN, en parallèle de R43 (1 fF : rien)
.param cg2=22n
* résistance série de la diode parasite supposée entre la masse et la broche BAT
* du TP4056 (1e6 : pas de diode)
.param rsub=0.5
* capacité réelle des condensateurs de 10 µF, en proportion de la valeur marquée
.param kc=1
* variantes : d16fuite=0 retire la fuite propre de D16 (on l'impose par Ifuite) ;
* d16max=1 et d22max=1 prennent les diodes au pire de la fiche ; d25=0 remplace
* D25 par un fil ; q6=0 retire Q6 ; thcoupe=1 coupe la thermistance, thcc=1 la
* met en court-circuit
.param d16fuite=1 d16max=0 d22max=0 d25=1 q6=1 thcoupe=0 thcc=0 stdbypin=0

* ------------------------------------------------------------------ monde extérieur
Vusb usb 0 dc 5
Vctl_usb ctl_usb 0 dc 1
Rusb usb usb_c {rusb}
Busb usb_c vbus I = V(usb_c,vbus)*(1e-12 + V(ctl_usb)/1m)

Vcell cp batn dc 3.7
Vctl_cell ctl_cell 0 dc 1
Rcell cp cq {rcell}
Lcell cq cr {lcell}
Bcell cr batp I = V(cr,batp)*(1e-12 + V(ctl_cell)/1m)

* seconde cellule, débranchée par défaut : sert aux essais où l'on remplace une
* batterie par une autre (alter Vcell2, alter Vctl_cell2)
Vcell2 cp2 batn dc -4.2
Vctl_cell2 ctl_cell2 0 dc 0
Rcell2 cp2 cq2 {rcell}
Lcell2 cq2 cr2 {lcell}
Bcell2 cr2 batp I = V(cr2,batp)*(1e-12 + V(ctl_cell2)/1m)

Vctl_isys ctl_isys 0 dc 0
Bsys vsys 0 I = V(ctl_isys)*tanh(max(V(vsys),0)/0.3)
Vctl_ibat ctl_ibat 0 dc 0
Bbat vbat 0 I = V(ctl_ibat)*tanh(max(V(vbat),0)/0.3)

* 3,3 V : régulateur idéal derrière VSYS (0,15 V de chute), pour les grilles
* et les rappels. Vctl_3v3 à 0 : 3,3 V absent.
Vctl_3v3 ctl_3v3 0 dc 1
B3v3 p3v3 0 V = V(ctl_3v3)*0.5*( V(vsys)-0.15+3.3 - sqrt((V(vsys)-0.15-3.3)^2 + 1e-4) )*0.5*(1+tanh(V(vsys)/0.05-3))

* broches de la puce
Vinh inh_src 0 dc 0
Rinh inh_src chg_inh 1e12
Rinh_fuite chg_inh 0 1e9
Viset iset_src 0 dc 0
Riset iset_src iset 30
Cdet vbus_det 0 5p

* ------------------------------------------------------------------ USB
R39 vbus vbus_amorti 1
C1 vbus_amorti c1e {10u*kc}
Rc1 c1e 0 5m
C39 vbus 0 1u
R5 vbus vbus_sense {r5}
R6 vbus_sense 0 {r6}
R7 vbus_sense vbus_det 100k
D24 0 vbus PESD5Z5V0
Ifuite vsys vbus dc 0

* ------------------------------------------------------------------ chargeur
XU2 vbus vbat prog ce temp chrg stdby 0 TP4056 params: rsub={rsub}
R8 prog 0 {r8}
R9 prog prog_x {r9}
XQ1 prog_x iset 0 AO3400A
R10 iset 0 100k
R42 prog prog_tp 10k
Ctp prog_tp 0 10p
R11 vbus temp {r11}
R12 temp 0 {r12}
Vtth tth 0 dc 25
.if (thcc==1)
Rth temp 0 1m
.elseif (thcoupe==1)
Rth temp 0 1e12
.else
Bth temp 0 I = V(temp)/({rth25}*exp({bth}*(1/(V(tth)+273.15)-1/298.15)))
.endif
C2 vbat c2e {10u*kc}
Rc2 c2e 0 5m
R13 p3v3 chrg 100k
R41 vbus stdby 100k
* essai : STDBY relié à une entrée 3,3 V, vue comme sa diode de protection
.if (stdbypin==1)
Dpin stdby p3v3 DPARASITE
.endif
.if (d25==1)
D25 vbus ce_pu D1N4148WS
.else
R25 vbus ce_pu 1m
.endif
R44 ce_pu ce {r44}
C40 ce 0 100n
XQ7 ce p3v3 q7_s AO3400A
R47 chg_inh q7_s {r47}

* ------------------------------------------------ batterie et protection
XQ2 batp q2_g vbat AO3401A_SEUIL params: dvto={dvto_q2}
.if (q6==1)
XQ6 q2_g q6_g vbat AO3401A_SEUIL params: dvto={dvto_q6}
.else
Cq6 q6_g vbat 645p
.endif
R43 q2_g batn {r43}
Cg2 q2_g batn {cg2}
R45 vbat batp {r45}
R46 batp q6_g {r46}
Vctl_q3 ctl_q3 0 dc 1
XU3 dw_vcc batn dw_od dw_oc dw_cs ctl_q3 DW01A params: auto={auto}
R14 vbat dw_vcc 100
C3 dw_vcc batn 100n
R15 dw_cs 0 1k
XQ3a prot_d dw_od batn FS8205A
XQ3b prot_d dw_oc 0 FS8205A
R16 vbat vbat_sense 470k
R17 vbat_sense 0 470k
C4 vbat_sense 0 100n

* ------------------------------------------- partage de charge
.if (d16fuite==0)
D16 vbus vsys DSK24_SANSFUITE
.elseif (d16max==1)
D16 vbus vsys DSK24_MAX
.else
D16 vbus vsys DSK24
.endif
.if (d22max==1)
D22 vbat vsys DSK24_MAX
.else
D22 vbat vsys DSK24
.endif
* Viq4 : ampèremètre, courant de VBAT vers VSYS à travers Q4
Viq4 vbat q4_d 0
XQ4 q4_d vbus vsys DMP1045U_SEUIL params: dvto={dvto_q4}
* C5, C6 et C13 : 10 µF chacun sur le nœud système (ponts JP2 et JP3 fermés)
C5 vsys c5e {30u*kc}
Rc5 c5e 0 2m
C38 vsys 0 100n
