1 2 3

# Tema 1 RL - Implementare switch
# Alexandru LICURICEANU 332CD

# Tabela de comutare

- Initializez o tablea goala, `mac_table`.
- Cand primesc un cadru, verific daca MAC-ul destinatie este de broadcast.

- Daca adresa destinatie este de tip unicast:
- Daca MAC-ul destinatie exista deja in `mac_table`, trimit cadrul pe interfata
asociat cu adresa MAC de destinatie.
- Daca nu gasesc MAC-ul destinatie in `mac_table`, trimit cadrul pe toate porturile,
cu exceptia portului de intrare.

- Daca adresa destinatie nu este de tip unicast, cadrul este trimis pe toate celelalte
porturi, in afara celui de intrare, pentru a ajunge la toate statiile.

# VLAN

- Mi-am definit functii ajutatoare care sa adauge si sa scoata tag-urile de VLAN si
sa modifice lungimea cadrului.

- Citesc si stochez ID-urile VLAN-urilor din fisierul de configuratie aferent switch-ului.
- Daca primesc un cadru de pe o interfata de tip trunk, ii scot tag-ul.
- Am plecat de la algoritmul de la tabela de comutare si am adus urmatoarele modificari:

- De fiecare data cand trimit un pachet verific:
- Daca portul pe care urmeaza sa trimit este de tipul access si are acelasi VLAN ID cu
cadrul pe care il trimit, inseamna ca am ajuns la un host-ul destinatie, deci trimit cadrul
fara tag.
- Daca portul pe care urmeaza sa trimit este de tipul trunk, trimit cadrul cu tag.

# STP

- Inainte de a porni bucla infinita a switch-ului, trimit Hello BPDU pe toate interfetele.
Fiecare switch se declara ca fiind root bridge-ul. Si initial toate porturile sunt blocate.
- In bucla infinita, verific daca pachetul are adresa destinatie "01:80:C2:00:00:00", caz in
care se executa functia care proceseaza datele din BPDU, `process_received_bpdu`.
- Daca am primit un BPDU care contine o prioritate mai mica decat cea a switch-ului, 
actualizez costul, deschid portul catre switch-ul cu prioritatea mai mica si le inchid pe 
restul in afara de cele de tip acces.  De asemenea, un nou BPDU care contine noul cost si
root bridge-ul ales este transmis catre toate interfetele switch-ului.
- La final, toate porturile root bridge-ului sunt deschise.
