Linux:
sqlitebrowser

Befehle zur maniplation:
ALTER TABLE measurements DROP COLUMN gateway_id;
ALTER TABLE measurements RENAME COLUMN timestamp_iso TO utms;
ALTER TABLE measurements RENAME COLUMN temp_aussen1 TO temperature1;
ALTER TABLE measurements RENAME COLUMN feuchte_aussen1 TO humidity1;
ALTER TABLE measurements RENAME COLUMN temp_aussen2 TO temperature2;
ALTER TABLE measurements RENAME COLUMN feuchte_aussen2 TO humidity2;
ALTER TABLE measurements RENAME COLUMN temp_aussen3 TO temperature3;
ALTER TABLE measurements RENAME COLUMN feuchte_aussen3 TO humidity3;
ALTER TABLE measurements RENAME COLUMN temp_innen TO temperatureIN;
ALTER TABLE measurements RENAME COLUMN feuchte_innen TO humidityIN;
ALTER TABLE measurements RENAME COLUMN batteriestatus TO battery;
