* Luciole² v0 : le port Grove, recopié de circuit.py (bloc « port Grove », rév. 0.5)
* et de netlist_voulue.txt. Fichier commun aux cas A1 à A4 : chaque cas l'inclut,
* puis ajoute les broches de la puce, les rails et l'accessoire.
*
* Nœuds, aux noms du schéma : v33 (+3V3), vled (VLED), port_pu, io1, io2,
* port_1x, port_2x, port_1, port_2 (broches 1 et 2 de J3), port_buf, port_buf_r,
* port_ecret.
* Ampèremètres (sources de 0 V) : i(Vi36) = courant que U10 envoie vers la ligne,
* i(Viq8), i(Viq9) = courant qui sort de la source de Q8, Q9 vers IO1, IO2,
* i(Viu11a), i(Viu11b) = courant qui entre dans U11 par chaque ligne.
*
* Réglages du calcul. Le rail d'écrêtage de U11 n'est tenu que par des diodes et
* des fuites de quelques nA : avec les réglages par défaut, ngspice ne trouve pas
* toujours le point de repos et se rabat sur un faux régime transitoire trop court
* pour charger C41. Ces réglages l'évitent ; lancer.sh signale tout repli.
.options gmin=1e-11 abstol=1e-11 itl1=500 itl2=500

* Valeurs du schéma, modifiables par « alterparam » dans les fichiers de cas.
.param r31=220 r32=220 r33=4.7k r34=4.7k r35=1meg r36=220 c41=100n
* JP4 : 1 mΩ = pont fermé (état de livraison) ; 1e12 = pont coupé
.param jp4=1m
* Transistors Q8, Q9 : fort=0 typique, fort=1 pire cas de la copie (seuil 1,6 V, 3 Ω)
.param fort=0
.param q_vto={fort == 1 ? 1.55 : 1.2948}
.param q_kp={fort == 1 ? 0.21 : 0.6472}
* U10 : seuil imposé (0 = typique), temps de propagation
.param u10_vth=0 u10_tpd=3n
* U11 : fuite du rail d'écrêtage (525 MΩ typique, 35 MΩ au pire)
.param u11_rf=525meg
* Capacités de piste, non mesurées : hypothèse 3 pF par nœud
.param cpiste=3p
* Correction essayée, absente du schéma : dserie=1 met une diode 1N4148WS en série
* avec R36, anode du côté de U10, pour que la ligne ne puisse rien renvoyer à U10.
.param dserie=0

XQ8  port_1x v33 q8s BSS138P vto={q_vto} kp={q_kp}
Viq8 q8s io1 0
XQ9  port_2x v33 q9s BSS138P vto={q_vto} kp={q_kp}
Viq9 q9s io2 0
R31  port_1x port_1 {r31}
R32  port_2x port_2 {r32}
R33  port_pu io1 {r33}
R34  port_pu io2 {r34}
R35  v33 port_pu {r35}

XU10 io2 port_pu port_buf vled 0 LV1T vthfix={u10_vth} tpd={u10_tpd}
R36  port_buf port_buf_r {r36}
Dser port_buf_r jp4d D4148S
Rser port_buf_r jp4d {dserie == 1 ? 1e12 : 1m}
.model D4148S d(is=2.5n n=1.8 rs=0.6 cjo=1p tt=4n bv=100)
Vi36 jp4d jp4a 0
RJP4 jp4a port_2 {jp4}

Viu11a port_1 u11a 0
Viu11b port_2 u11b 0
XU11 u11a u11b port_ecret 0 USBLC6 rfuite={u11_rf}
C41  port_ecret 0 {c41}

Cio1 io1 0 {cpiste}
Cio2 io2 0 {cpiste}
Cp1  port_1 0 {cpiste}
Cp2  port_2 0 {cpiste}
Cpu  port_pu 0 {cpiste}
