# Diccionario de datos - motoshop2024

> Generado desde information_schema (MySQL 5.0.45). Solo lectura.

## facventas
Motor: MyISAM · Filas aprox: 7307 · Filas reales: 7307

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| numfven | varchar(20) | NO |  | MUL |
| codclas | varchar(4) | NO |  | MUL |
| nomdoc | varchar(100) | NO | FACTURA DE VENTA |  |
| prefven | varchar(8) | NO | FV |  |
| fecfven | datetime | NO | 2000-01-20 00:00:00 |  |
| codciu | varchar(6) | NO |  | MUL |
| nitter | varchar(15) | NO |  | MUL |
| digfven | char(2) | NO |  |  |
| clifven | varchar(120) | NO |  |  |
| dirfven | varchar(100) | NO |  |  |
| telfven | varchar(50) | NO |  |  |
| nitvend | varchar(15) | NO |  | MUL |
| venfven | varchar(120) | NO |  |  |
| codpag | varchar(4) | NO | - |  |
| diasfven | smallint(6) | NO | 0 |  |
| subfven | double | NO | 0 |  |
| totdct | double | NO | 0 |  |
| totiva | double | NO | 0 |  |
| totipo | double | NO | 0 |  |
| retfte | double | NO | 0 |  |
| retiva | double | NO | 0 |  |
| retica | double | NO | 0 |  |
| retcre | double | NO | 0 |  |
| ajuspe | double | NO | 0 |  |
| totfven | double | NO | 0 |  |
| obsfven | varchar(400) | NO |  |  |
| estfven | char(1) | NO |  |  |
| codemp | varchar(15) | NO |  | MUL |
| horfven | tinyint(3) | NO | 1 |  |
| tipcre | char(1) | NO | N |  |
| codres | varchar(4) | NO |  | MUL |
| codcos | varchar(6) | NO |  | MUL |
| codzon | varchar(4) | NO |  |  |
| codcaj | varchar(4) | NO |  | MUL |
| comipor | float | NO | 0 |  |
| empcod | varchar(3) | NO |  | MUL |
| numcru | varchar(20) | NO |  | MUL |
| clascru | varchar(4) | NO |  | MUL |
| perdes | date | NO | 2010-01-01 |  |
| perhas | date | NO | 2010-01-01 |  |
| codsuc | varchar(15) | NO |  | MUL |
| nomest | varchar(2) | NO |  |  |
| nomuso | varchar(2) | NO |  |  |
| nomrut | varchar(100) | NO |  |  |
| nomzon | varchar(100) | NO |  |  |
| salant | double | NO | 0 |  |
| numdeu | smallint(3) | NO | 0 |  |
| texres | varchar(250) | NO |  |  |
| codpla | varchar(30) | NO |  |  |
| codmes | varchar(4) | NO |   |  |
| comanum | varchar(20) | NO |   |  |
| nomcos | varchar(50) | NO |  |  |
| cauret | char(1) | NO |  |  |
| turno1 | char(1) | NO | 0 |  |
| estfele | char(1) | NO | N |  |
| resfele | int(6) | NO | 0 |  |
| propina | double | NO | 0 |  |
| agrupa | char(1) | NO |  |  |
| tipdomi | char(1) | NO |  |  |
| lectant | int(11) | NO | 0 |  |
| lectact | int(11) | NO | 0 |  |
| consumo | int(11) | NO | 0 |  |
| tiplect | char(1) | NO |  |  |
| docext | varchar(20) | NO |  |  |
| corele | varchar(100) | NO |  |  |

Indices:
  - clascru uniq=no seq=1 campo=clascru
  - codcaj uniq=no seq=1 campo=codcaj
  - codciu uniq=no seq=1 campo=codciu
  - codclas uniq=no seq=1 campo=codclas
  - codcos uniq=no seq=1 campo=codcos
  - codemp uniq=no seq=1 campo=codemp
  - codres uniq=no seq=1 campo=codres
  - codsuc uniq=no seq=1 campo=codsuc
  - empcod uniq=no seq=1 campo=empcod
  - nitter uniq=no seq=1 campo=nitter
  - nitvend uniq=no seq=1 campo=nitvend
  - numcru uniq=no seq=1 campo=numcru
  - numfven uniq=no seq=1 campo=numfven

## detfventas
Motor: MyISAM · Filas aprox: 32745 · Filas reales: 32745

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| numfven | varchar(20) | NO |  | MUL |
| codclas | varchar(4) | NO |  | MUL |
| codprod | varchar(20) | NO |  | MUL |
| nomdet | varchar(300) | NO |  |  |
| candet | double | NO | 0 |  |
| valuni | double | NO | 0 |  |
| dctpor | float | NO | 0 |  |
| dctpes | double | NO | 0 |  |
| ivapor | float | NO | 0 |  |
| ivapes | double | NO | 0 |  |
| ipopor | float | NO | 0 |  |
| ipopes | double | NO | 0 |  |
| totdet | double | NO | 0 |  |
| cosprod | double | NO | 0 |  |
| sernum | varchar(40) | NO |  |  |
| serfec | varchar(10) | NO |  |  |
| obsdet | varchar(200) | NO |  |  |
| tipdet | char(2) | NO | P |  |
| codpor | varchar(4) | NO | 0 | MUL |
| codpor2 | varchar(4) | NO | 0 |  |
| codcos | varchar(6) | NO |  | MUL |
| codbod | varchar(4) | NO |  | MUL |
| codmed | varchar(3) | NO |  | MUL |
| divmul | char(1) | NO | M |  |
| facumed | double | NO | 1 |  |
| presdet | varchar(100) | NO |  |  |
| devcam | char(2) | NO | NO |  |
| numite | smallint(6) | NO | 1 |  |
| iterel | smallint(6) | NO | 0 |  |
| cruclas | varchar(4) | NO |  | MUL |
| crunum | varchar(20) | NO |  | MUL |
| tipipo | varchar(2) | NO |  |  |
| tiesub | char(1) | NO |  |  |
| puntos | double | NO | 0 |  |
| grudet | varchar(1) | NO |  |  |
| nitfor | varchar(15) | NO |  | MUL |
| aplcomi | char(1) | NO | N |  |
| porcomi | float | NO | 0 |  |

Indices:
  - codbod uniq=no seq=1 campo=codbod
  - codclas uniq=no seq=1 campo=codclas
  - codcos uniq=no seq=1 campo=codcos
  - codmed uniq=no seq=1 campo=codmed
  - codpor uniq=no seq=1 campo=codpor
  - codprod uniq=no seq=1 campo=codprod
  - cruclas uniq=no seq=1 campo=cruclas
  - crunum uniq=no seq=1 campo=crunum
  - nitfor uniq=no seq=1 campo=nitfor
  - numfven uniq=no seq=1 campo=numfven

## detapago
Motor: MyISAM · Filas aprox: 9315 · Filas reales: 9315

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| numnum | varchar(20) | NO |  | MUL |
| codclas | varchar(4) | NO |  | MUL |
| predoc | varchar(8) | NO |  |  |
| numite | smallint(6) | NO | 0 |  |
| fecdoc | datetime | NO | 2000-01-20 00:00:00 |  |
| docodet | tinyint(3) | NO | 0 |  |
| valpag | double | NO | 0 |  |
| valefe | double | NO | 0 |  |
| despag | varchar(100) | NO |  |  |
| numpag | varchar(20) | NO |  |  |
| fecche | date | NO | 2000-01-20 |  |
| numapr | varchar(20) | NO |  |  |
| soldeb | double | NO | 0 |  |
| solcre | double | NO | 0 |  |
| codpag | varchar(4) | NO |  | MUL |
| afepag | tinyint(3) | NO | 0 |  |
| codban | varchar(8) | NO |  | MUL |
| codtar | varchar(4) | NO |  | MUL |
| estado | char(1) | NO | B |  |
| tipcmen | char(1) | NO |  |  |
| nitter | varchar(15) | NO |  | MUL |
| codemp | varchar(15) | NO |  |  |
| codcaj | varchar(4) | NO |  |  |
| turno1 | char(1) | NO | 0 |  |
| fecven | date | NO | 2000-01-01 |  |

Indices:
  - codban uniq=no seq=1 campo=codban
  - codclas uniq=no seq=1 campo=codclas
  - codpag uniq=no seq=1 campo=codpag
  - codtar uniq=no seq=1 campo=codtar
  - nitter uniq=no seq=1 campo=nitter
  - numnum uniq=no seq=1 campo=numnum

## formapago
Motor: MyISAM · Filas aprox: 20 · Filas reales: 20

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codpag | varchar(4) | NO |  | PRI |
| forpag | varchar(100) | NO |  |  |
| afepag | tinyint(3) | NO | 0 |  |
| tippag | tinyint(3) | NO | 0 |  |
| codcaj | varchar(4) | NO |  | MUL |
| codban | varchar(8) | NO |  | MUL |
| codcue | varchar(12) | NO |  | MUL |
| facven | char(2) | NO | NO |  |
| venpos | char(2) | NO | NO |  |
| ndcxc | char(2) | NO | NO |  |
| nccxc | char(2) | NO | NO |  |
| compra | char(2) | NO | NO |  |
| ndcxp | char(2) | NO | NO |  |
| nccxp | char(2) | NO | NO |  |
| coming | char(2) | NO | NO |  |
| comegr | char(2) | NO | NO |  |
| devpos | char(2) | NO | NO |  |
| financ | char(2) | NO | NO |  |
| oblifin | char(2) | NO | NO |  |
| nomemp | char(2) | NO | NO |  |
| numcon | bigint(20) | NO | 0 |  |
| empsino | char(1) | NO | N |  |
| anting | char(2) | NO | SI |  |
| antegr | char(2) | NO | SI |  |
| codaux1 | varchar(10) | NO |  |  |
| codfele | varchar(3) | NO |  | MUL |

Indices:
  - codban uniq=no seq=1 campo=codban
  - codcaj uniq=no seq=1 campo=codcaj
  - codcue uniq=no seq=1 campo=codcue
  - codfele uniq=no seq=1 campo=codfele
  - PRIMARY uniq=si seq=1 campo=codpag

## cajas
Motor: MyISAM · Filas aprox: 1 · Filas reales: 1

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codcaj | varchar(4) | NO |  | PRI |
| descaj | varchar(50) | NO | CAJA UNO |  |
| indgen | char(3) | NO | GEN |  |
| titfac | varchar(50) | NO | FACTURA DE VENTA |  |
| codres | varchar(4) | NO |  | MUL |
| resdian | char(2) | NO | NO |  |
| numres | varchar(20) | NO |  |  |
| fecres | date | NO | 2000-01-01 |  |
| numini | bigint(20) | NO | 1 |  |
| numfin | bigint(20) | NO | 100 |  |
| numauto | char(2) | NO | SI |  |
| fecauto | char(2) | NO | NO |  |
| conres | bigint(20) | NO | 1 |  |
| avires | bigint(20) | NO | 0 |  |
| preres | varchar(8) | NO |  |  |
| imptiq | char(2) | NO | NO |  |
| codpag | varchar(4) | NO |  |  |
| empsino | char(1) | NO | N |  |
| maqnom | varchar(250) | NO |  |  |
| afeclas | varchar(4) | NO | S15 |  |
| prefgen | char(1) | NO | S |  |
| numplac | varchar(50) | NO |  |  |
| ubicaj | varchar(100) | NO |  |  |
| codiven | varchar(30) | NO |  |  |

Indices:
  - codres uniq=no seq=1 campo=codres
  - PRIMARY uniq=si seq=1 campo=codcaj

## cajaspago
Motor: MyISAM · Filas aprox: 1 · Filas reales: 1

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codcaj | varchar(4) | NO |  | PRI |
| nomcaj | varchar(100) | NO |  |  |
| puccaj | varchar(12) | NO |  |  |

Indices:
  - PRIMARY uniq=si seq=1 campo=codcaj

## productos
Motor: MyISAM · Filas aprox: 6493 · Filas reales: 6493

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codprod | varchar(20) | NO |  | PRI |
| codbar | varchar(40) | NO |  | MUL |
| nomprod | varchar(200) | NO |  |  |
| codmed | varchar(3) | NO |  | MUL |
| valmed | double | NO | 0 |  |
| presen | varchar(30) | NO |  |  |
| incserl | char(2) | NO | SI |  |
| inccum | char(2) | NO | NO |  |
| stockmin | double | NO | 0 |  |
| stockmax | double | NO | 0 |  |
| exiprod | double | NO | 0 |  |
| cosprod | double | NO | 0 |  |
| cosman | double | NO | 0 |  |
| cosulc | double | NO | 0 |  |
| cosant | double | NO | 0 |  |
| coskar | double | NO | 0 |  |
| tipcos | char(2) | NO | NO |  |
| pvsini | double | NO | 0 |  |
| pvconi | double | NO | 0 |  |
| pvtipo | char(1) | NO | 1 |  |
| menopre | double | NO | 0 |  |
| codpor | varchar(4) | NO |  | MUL |
| codpor2 | varchar(4) | NO |  |  |
| codpor3 | varchar(4) | NO |  |  |
| codlin1 | varchar(4) | NO |  | MUL |
| codlin2 | char(4) | NO |  |  |
| codlin3 | char(4) | NO |  |  |
| codlin4 | char(4) | NO |  |  |
| codlin5 | char(4) | NO |  |  |
| codlin6 | char(4) | NO |  |  |
| actprod | char(1) | NO | A |  |
| reginvi | varchar(30) | NO |  |  |
| regcum | varchar(30) | NO | NO |  |
| desprod | varchar(800) | NO |  |  |
| fotprod | varchar(255) | NO |  |  |
| fecapa | date | NO | 2013-01-01 |  |
| manser | char(1) | NO | N |  |
| moddet | char(1) | NO | N |  |
| pidfor | char(1) | NO |  |  |
| masiva | char(1) | NO |  |  |
| pidecos | char(1) | NO |  |  |
| fsinex | char(1) | NO |  |  |
| impinvi | char(2) | NO | NO |  |
| modipre | char(1) | NO | S |  |
| calcuni | char(1) | NO | N |  |
| noesven | char(1) | NO | N |  |
| infmin | char(1) | NO | N |  |
| tipsub | char(1) | NO |  |  |
| tipser | varchar(30) | NO |  |  |
| nitter | varchar(15) | NO |  | MUL |
| refprov | varchar(50) | NO |  |  |
| regica | varchar(30) | NO |  |  |
| titufab | varchar(100) | NO |  |  |
| valform | double | NO | 1 |  |
| actfij | char(1) | NO |  |  |
| nominv | char(1) | NO | N |  |
| actupr | char(1) | NO | N |  |
| aproxi | char(1) | NO | 0 |  |
| aplcomi | char(1) | NO | N |  |
| porcomi | float | NO | 0 |  |
| porutil | float | NO | 0 |  |
| factobs | float | NO | 0 |  |
| prbase | double | NO | 0 |  |
| minuto | smallint(3) | NO | 0 |  |
| puntos | double | NO | 0 |  |
| codcos | varchar(6) | NO |  | MUL |
| auxdet | varchar(150) | NO |  |  |
| multiplo | double | NO | 1 |  |
| inviica | char(1) | NO | 1 |  |
| lugimp | varchar(50) | NO |  |  |
| pesopro | double | NO | 0 |  |
| valpor2 | double | NO | 0 |  |
| pidobs1 | char(1) | NO |  |  |
| pidobs2 | char(1) | NO |  |  |
| lotcos | char(1) | NO |  |  |
| lotobl | char(1) | NO |  |  |
| codbod | varchar(4) | NO |  |  |

Indices:
  - codbar uniq=no seq=1 campo=codbar
  - codcos uniq=no seq=1 campo=codcos
  - codlin1 uniq=no seq=1 campo=codlin1
  - codmed uniq=no seq=1 campo=codmed
  - codpor uniq=no seq=1 campo=codpor
  - nitter uniq=no seq=1 campo=nitter
  - PRIMARY uniq=si seq=1 campo=codprod

## compras
Motor: MyISAM · Filas aprox: 811 · Filas reales: 811

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| numcom | varchar(20) | NO |  | MUL |
| codclas | varchar(4) | NO |  | MUL |
| nomdoc | varchar(100) | NO | COMPRA |  |
| precom | varchar(8) | NO | COM |  |
| feccom | datetime | NO | 2000-01-20 00:00:00 |  |
| diascot | int(11) | NO | 0 |  |
| faccom | varchar(20) | NO |  |  |
| nitter | varchar(15) | NO |  | MUL |
| digcom | char(2) | NO |  |  |
| codsuc | varchar(15) | NO |  | MUL |
| procom | varchar(120) | NO |  |  |
| dircom | varchar(100) | NO |  |  |
| telcom | varchar(50) | NO |  |  |
| codpag | varchar(4) | NO | - |  |
| subcom | double | NO | 0 |  |
| totdct | double | NO | 0 |  |
| totiva | double | NO | 0 |  |
| totipo | double | NO | 0 |  |
| retfte | double | NO | 0 |  |
| retiva | double | NO | 0 |  |
| retica | double | NO | 0 |  |
| retcre | double | NO | 0 |  |
| ajuspe | double | NO | 0 |  |
| totcom | double | NO | 0 |  |
| obscom | varchar(400) | NO |  |  |
| estcom | char(1) | NO |  |  |
| codemp | varchar(15) | NO |  | MUL |
| horcom | tinyint(3) | NO | 1 |  |
| codres | varchar(4) | NO |  | MUL |
| numcru | varchar(20) | NO |  | MUL |
| clascru | varchar(4) | NO |  | MUL |
| codcos | varchar(6) | NO |  | MUL |
| codzon | varchar(4) | NO |  |  |
| empcod | varchar(3) | NO |  | MUL |
| nitvend | varchar(15) | NO |  | MUL |
| codpla | varchar(30) | NO |  |  |
| artsol | varchar(50) | NO |  |  |
| marsol | varchar(50) | NO |  |  |
| modsol | varchar(50) | NO |  |  |
| trarea | varchar(400) | NO |  |  |
| recesp | varchar(400) | NO |  |  |
| horini | datetime | NO | 2000-01-01 00:00:00 |  |
| horfin | datetime | NO | 2000-01-01 00:00:00 |  |
| codmes | varchar(4) | NO |   |  |
| estado | char(1) | NO | A |  |
| garfac | varchar(30) | NO |  |  |
| verifi | char(1) | NO |  |  |
| cauret | char(1) | NO |  |  |
| porrfte | float | NO | 0 |  |
| agrupa | char(1) | NO |  |  |
| corele | varchar(100) | NO |  |  |

Indices:
  - clascru uniq=no seq=1 campo=clascru
  - codclas uniq=no seq=1 campo=codclas
  - codcos uniq=no seq=1 campo=codcos
  - codemp uniq=no seq=1 campo=codemp
  - codres uniq=no seq=1 campo=codres
  - codsuc uniq=no seq=1 campo=codsuc
  - empcod uniq=no seq=1 campo=empcod
  - nitter uniq=no seq=1 campo=nitter
  - nitvend uniq=no seq=1 campo=nitvend
  - numcom uniq=no seq=1 campo=numcom
  - numcru uniq=no seq=1 campo=numcru

## detcompras
Motor: MyISAM · Filas aprox: 12476 · Filas reales: 12476

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| numcom | varchar(20) | NO |  | MUL |
| codclas | varchar(4) | NO |  | MUL |
| codprod | varchar(20) | NO |  | MUL |
| nomdet | varchar(300) | NO |  |  |
| candet | double | NO | 0 |  |
| valuni | double | NO | 0 |  |
| dctpor | float | NO | 0 |  |
| dctpes | double | NO | 0 |  |
| ivapor | float | NO | 0 |  |
| ivapes | double | NO | 0 |  |
| ipopor | float | NO | 0 |  |
| ipopes | double | NO | 0 |  |
| totdet | double | NO | 0 |  |
| obsdet | varchar(400) | NO |  |  |
| cosprod | double | NO | 0 |  |
| sernum | varchar(40) | NO |  |  |
| serfec | varchar(10) | NO |  |  |
| tipdet | char(2) | NO | P |  |
| codpor | varchar(4) | NO | 0 | MUL |
| codpor2 | varchar(4) | NO | 0 |  |
| codbod | varchar(4) | NO |  | MUL |
| codcos | varchar(6) | NO |  | MUL |
| codmed | varchar(3) | NO |  | MUL |
| divmul | char(1) | NO | M |  |
| facumed | double | NO | 1 |  |
| numite | smallint(6) | NO | 1 |  |
| iterel | smallint(6) | NO | 0 |  |
| cruclas | varchar(4) | NO |   |  |
| crunum | varchar(20) | NO |   |  |
| tipipo | varchar(2) | NO |  |  |
| nitfor | varchar(15) | NO |  | MUL |
| horini | datetime | NO | 2000-01-01 00:00:00 |  |
| horfin | datetime | NO | 2000-01-01 00:00:00 |  |
| multiplo | double | NO | 1 |  |
| nomtec | varchar(120) | NO |  |  |
| factpor | float | NO | 0 |  |
| prbase | double | NO | 0 |  |

Indices:
  - codbod uniq=no seq=1 campo=codbod
  - codclas uniq=no seq=1 campo=codclas
  - codcos uniq=no seq=1 campo=codcos
  - codmed uniq=no seq=1 campo=codmed
  - codpor uniq=no seq=1 campo=codpor
  - codprod uniq=no seq=1 campo=codprod
  - nitfor uniq=no seq=1 campo=nitfor
  - numcom uniq=no seq=1 campo=numcom

## auxinventario
Motor: MyISAM · Filas aprox: 246 · Filas reales: 246

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codlis | char(3) | NO |  | MUL |
| nomlis | varchar(100) | NO |  |  |
| codlin1 | varchar(4) | NO |  |  |
| nomlin | varchar(100) | NO |  |  |
| codlin2 | varchar(4) | NO |  |  |
| nomlin2 | varchar(100) | NO |  |  |
| codlin3 | varchar(4) | NO |  |  |
| nomlin3 | varchar(100) | NO |  |  |
| codlin4 | varchar(4) | NO |  |  |
| nomlin4 | varchar(100) | NO |  |  |
| codlin5 | varchar(4) | NO |  |  |
| nomlin5 | varchar(100) | NO |  |  |
| codlin6 | varchar(4) | NO |  |  |
| nomlin6 | varchar(100) | NO |  |  |
| codbod | varchar(4) | NO |  |  |
| nombod | varchar(100) | NO |  |  |
| nitter | varchar(15) | NO |  |  |
| nomter | varchar(120) | NO |  |  |
| numdoc | varchar(20) | NO |  |  |
| nomdoc | varchar(100) | NO |  |  |
| codprod | varchar(20) | NO |  | MUL |
| sernum | varchar(40) | NO |  |  |
| nomprod | varchar(250) | NO |  |  |
| unimed | varchar(150) | NO |  |  |
| valor1 | double | NO | 0 |  |
| valor2 | double | NO | 0 |  |
| valor3 | double | NO | 0 |  |
| valor4 | double | NO | 0 |  |
| valor5 | double | NO | 0 |  |
| docfec | datetime | NO | 2000-01-20 00:00:00 |  |
| docnum | varchar(30) | NO |  |  |
| nomsub | varchar(30) | NO |  |  |
| multiplo | double | NO | 1 |  |
| codcos | varchar(6) | NO |  | MUL |
| nomcos | varchar(100) | NO |  |  |

Indices:
  - codcos uniq=no seq=1 campo=codcos
  - codlis uniq=no seq=1 campo=codlis
  - codprod uniq=no seq=1 campo=codprod

## auxkardex
Motor: MyISAM · Filas aprox: 0 · Filas reales: 0

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| feckar | datetime | NO | 2000-01-20 00:00:00 |  |
| horkar | tinyint(3) | NO | 0 |  |
| entsal | tinyint(3) | NO | 0 |  |
| detkar | varchar(80) | NO |  |  |
| cankar | double | NO | 0 |  |
| coskar | double | NO | 0 |  |
| tipkar | char(1) | NO | 1 |  |
| clase | varchar(15) | NO |  |  |
| numdoc | varchar(20) | NO |  |  |
| reclase | varchar(15) | NO |  |  |
| renumdoc | varchar(20) | NO |  |  |
| codemp | varchar(15) | NO |  |  |
| codclas | varchar(4) | NO |  |  |
| codprod | varchar(20) | NO |  |  |
| codbod | varchar(4) | NO |  |  |
| codcos | varchar(6) | NO |  |  |

Indices:

## detimpuestos
Motor: MyISAM · Filas aprox: 4 · Filas reales: 4

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codpor | varchar(4) | NO | 0 | PRI |
| codimp | char(3) | NO | 0 |  |
| poroval | varchar(2) | NO | SI |  |
| porimp | float | NO | 0 |  |
| valfij | double | NO | 0 |  |
| despor | varchar(50) | NO |  |  |
| codaux1 | varchar(10) | NO |  |  |
| sigla | varchar(4) | NO |  |  |
| inaimp | char(1) | NO | N |  |
| codele | char(2) | NO | 01 |  |
| tipimp | varchar(2) | NO | 01 |  |

Indices:
  - PRIMARY uniq=si seq=1 campo=codpor

## bodegas
Motor: MyISAM · Filas aprox: 1 · Filas reales: 1

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codbod | varchar(4) | NO |  | PRI |
| nombod | varchar(100) | NO |  |  |
| telbod | varchar(30) | NO |  |  |
| ubibod | varchar(100) | NO |  |  |
| resbod | varchar(100) | NO |  |  |

Indices:
  - PRIMARY uniq=si seq=1 campo=codbod

## undmedidas
Motor: MyISAM · Filas aprox: 9 · Filas reales: 9

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codmed | varchar(3) | NO |  | MUL |
| nommed | varchar(50) | NO |  |  |
| medpres | varchar(15) | NO |  |  |
| codele | varchar(3) | NO |  |  |

Indices:
  - codmed uniq=no seq=1 campo=codmed

## factorfin
Motor: MyISAM · Filas aprox: 24 · Filas reales: 24

| Campo | Tipo | Nulo | Default | Clave |
|---|---|---|---|---|
| codfac | varchar(4) | NO |  | PRI |
| desfac | varchar(50) | NO |  |  |
| valfac | double | NO | 0 |  |
| numcuo | tinyint(3) | NO | 0 |  |
| porfin | float | NO | 0 |  |

Indices:
  - PRIMARY uniq=si seq=1 campo=codfac

## Formas de pago (formapago)

## Impuestos (detimpuestos)
